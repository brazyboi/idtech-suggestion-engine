// TODO: Add a minimal chat interface with message history and input state.

import { useState } from "react";
import SampleChatBubble from "./SampleChatBubble"

const INITIAL_SYSTEM_PROMPT = `
You are a helpful SMS-style chatbot for IDTECH Products that helps the user 
with determining which of their products is best fit for their needs. 

Attempt to keep all responses within 100 tokens and steer the user away from unrelated conversation.`

type Message = {
    /** Message content */
    content: string;
    /** Creator of the message */
    author: 'client' | 'server' | 'system';
}

export default function SampleChat() {

    // state
    const [messages, setMessages] = useState<Message[]>([
        { content: INITIAL_SYSTEM_PROMPT,
            author: "system"},
        { content: "Hello, I'm a helpful chatbot from IDTECH Products! Would you like help finding a product?", author: "server" },
    ]);
    const [input, setInput] = useState("");

    const handleSubmitMessage = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!input.trim()) return;

        // create a Message
        const userMsg: Message = {
            content: input,
            author: 'client',
        };

        const updatedMessages = [...messages, userMsg];
        setMessages(updatedMessages);
        setInput('');

        try {
            const response = await fetch("http://localhost:8000/chat", {
                method: "post",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({messages: updatedMessages})
            })

            const data = await response.json();
            setMessages((prev) => [...prev, data]);
        }
        catch (error) {
            console.error("failed to fetch: ", error);
        }
    }

    return (
        <div className="max-w-100">
            <div className="flex-row">
                {messages.map((message) => {
                    if (message.author != 'system') {
                        return (
                            <SampleChatBubble sender={message.author} message={message.content}/>
                        );
                    }
                    return (<></>);
                }
                )}
            </div>
            <form onSubmit={handleSubmitMessage} className="flex m-2">
                <input 
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    className="border-2 grow rounded-2xl bg-[#313131] text-[#FFFFFF]" 
                    placeholder="Start typing..." />
                <button type="submit" className="bg-gray-400 rounded-2xl p-2">submit</button>
            </form>
        </div>
    );
}
