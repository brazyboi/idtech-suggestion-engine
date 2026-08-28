import os
import json
from openai import OpenAI
from typing import List, Dict, Any
from dotenv import load_dotenv
from .prompts import build_chat_prompt, TOOLS
from ..engine.rulesEngine.product_filtering import product_filtering
from ..db.session import SessionLocal
from ..engine.solution_schemas import RecommendationBundle

# Ensure environment variables are loaded
load_dotenv()

class LLMClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI API key missing. Set OPENAI_API_KEY or OPENAI_ADMIN_KEY environment variable "
                "or add it to a .env file (e.g. OPENAI_API_KEY=sk-...)."
            )

        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"

    def get_chat_response(self, message: str, history: List[Dict[str, str]], force_recommendation: bool = False) -> Dict[str, Any]:
        """
        Orchestrates the flow: Text -> Params -> Tool Call -> Result -> Explanation -> JSON.
        """
        messages = build_chat_prompt(message, history)

        # If caller requests to force a recommendation, add a direct instruction
        # so the model returns a RecommendationBundle JSON even if some interview
        # questions are missing. The model should make reasonable assumptions.
        if force_recommendation:
            messages.append({
                "role": "system",
                "content": (
                    "FORCE_RECOMMENDATION: Produce a valid RecommendationBundle JSON object "
                    "containing keys `hardware_items`, `hardware_name`, and `explanation`. "
                    "Make reasonable assumptions for any missing user details and choose the best-fit hardware. "
                    "Return only JSON (no surrounding commentary)."
                )
            })
       
        # First call to identify constraints and call tools
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if not tool_calls:
            return {"content": response_message.content} # just talk to user if no tool calls

        # Handle Tool Calls
        messages.append(response_message)

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            if function_name == "product_filtering":
                # Execute database filtering
                db = SessionLocal()
                try:
                    # product_filtering expects (db, constraints)
                    raw_results = product_filtering(db, args.get("constraints", {}))
                    content = json.dumps(raw_results)
                finally:
                    db.close()

                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": content,
                })

        # Final call to generate the RecommendationBundle and Explanation
        final_response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        raw_json = json.loads(final_response.choices[0].message.content)

        # If the model returned an intermediate constraints map (e.g. keys like
        # `input_power_1`, `param_1`, `model_name_1`) instead of a
        # RecommendationBundle, try to interpret those constraints, call
        # product_filtering, and synthesize a RecommendationBundle automatically.
        constraint_keys = [k for k in raw_json.keys() if k.startswith("input_power_") or k.startswith("param_") or k.startswith("model_name_") or k.startswith("operate_temperature_")]
        if constraint_keys and "hardware_items" not in raw_json:
            # Build a best-effort constraints dict from the returned params
            constraints = {}
            # input_power
            for k, v in raw_json.items():
                if k.startswith("input_power_") and isinstance(v, str) and v:
                    constraints["input_power"] = v.strip('%')
                    break
            # operate_temperature
            for k, v in raw_json.items():
                if k.startswith("operate_temperature_") and isinstance(v, str) and v:
                    constraints["operate_temperature"] = v.strip('%')
                    break
            # collect params as extra_specs_filter
            extras = []
            for k, v in raw_json.items():
                if k.startswith("param_") and isinstance(v, str) and v:
                    extras.append(v.strip('%'))
            if extras:
                constraints["extra_specs_filter"] = ",".join(extras)
            # model_name -> search_query
            for k, v in raw_json.items():
                if k.startswith("model_name_") and isinstance(v, str) and v:
                    constraints["search_query"] = v.strip('%')
                    break

            # Query DB for matching products
            db = SessionLocal()
            try:
                results = product_filtering(db, constraints)
            finally:
                db.close()

            # If we found matches, synthesize a RecommendationBundle
            if results:
                hw_items = []
                for r in results[:3]:
                    hw_items.append({
                        "name": r.get("model_name") or r.get("name") or "Unknown",
                        "role": "Primary Card Reader",
                        "technical_specs": r,
                    })

                bundle = {
                    "hardware_items": hw_items,
                    "hardware_name": hw_items[0]["name"] if hw_items else "",
                    "software": [],
                    "highlights": ["Auto-generated recommendation"],
                    "explanation": "Synthesized recommendation from inferred constraints.",
                    "installation_docs": [],
                }

                try:
                    # Validate structure using RecommendationBundle
                    RecommendationBundle(**bundle)
                    return bundle
                except Exception:
                    return bundle

        # If it looks like a RecommendationBundle, validate it
        if "hardware_items" in raw_json:
            try:
                bundle = RecommendationBundle(**raw_json)
                return bundle.model_dump()
            except Exception:
                # Fallback to raw if validation fails
                return raw_json
        
        return raw_json

# Instantiate the client
_client_instance = LLMClient()

# Exported function for easy access
def get_chat_response(message: str, history: List[Dict[str, str]], force_recommendation: bool = False) -> Dict[str, Any]:
    return _client_instance.get_chat_response(message, history, force_recommendation)
