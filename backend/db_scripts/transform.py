import os, json, re
from bs4 import BeautifulSoup

# Synonyms to match PDF keys to SQL columns
COLUMN_MAPPING = {
    'operate_temperature': ['operating temperature', 'temperatures', 'operating temp'],
    'input_power': ['power requirements', 'input power', 'power'],
    'ip_rating': ['ingress protection rating', 'ip rating'],
    'ik_rating': ['ik rating', 'vandal resistance', 'impact rating'],
    'interface': ['interface', 'connectivity']
}

def clean_model_name(filename):
    # model name extracted from filename
    return filename.split('_Datasheet')[0].replace('_', ' ')

def process_files():
    sql_statements = []
    # Walk the directory structure to find the nested _middle.json files
    for root, dirs, files in os.walk("./raw_extraction"):
        for file in files:
            if file.endswith("_middle.json"):
                filepath = os.path.join(root, file)
                with open(filepath) as f:
                    data = json.load(f)
                    model_name = clean_model_name(file)

                    raw_specs = {}
                    # Tables are nested under blocks, lines, and spans.
                    for page in data.get('pdf_info', []):
                        for block in page.get('para_blocks', []):
                            # Search recursively for 'html' in the block structure
                            if 'blocks' in block:
                                for sub_block in block['blocks']:
                                    if 'lines' in sub_block:
                                        for line in sub_block['lines']:
                                            if 'spans' in line:
                                                for span in line['spans']:
                                                    if span.get('type') == 'table' and 'html' in span:
                                                        soup = BeautifulSoup(span['html'], 'html.parser')
                                                        for row in soup.find_all('tr'):
                                                            cells = [td.get_text(strip=True) for td in row.find_all('td')]
                                                            if len(cells) >= 2:
                                                                # The final two cells contain the key and value.
                                                                key = cells[-2].lower()
                                                                val = cells[-1]
                                                                raw_specs[key] = val

                    # Map to Schema
                    final_fields = {col: 'NULL' for col in COLUMN_MAPPING}
                    extra_specs = {}

                    for key, val in raw_specs.items():
                        # 1. Value-based extraction for IP/IK ratings
                        ip_match = re.search(r'IP\s?\d{2}', val, re.I)
                        if ip_match:
                            final_fields['ip_rating'] = f"'{ip_match.group().upper()}'"
                        
                        ik_match = re.search(r'IK\s?\d{2}', val, re.I)
                        if ik_match:
                            final_fields['ik_rating'] = f"'{ik_match.group().upper()}'"

                        # 2. Standard mapping logic
                        matched = False
                        for col, synonyms in COLUMN_MAPPING.items():
                            if any(syn in key for syn in synonyms):
                                # Special handling for merged temperatures
                                if col == 'operate_temperature' and ';' in val:
                                    operating = val.split(';')[0].replace('(Operating)', '').strip()
                                    final_fields[col] = f"'{operating}'"
                                    extra_specs['storage_temperature'] = val.split(';')[1].replace('(Storage)', '').strip()
                                elif col not in ['ip_rating', 'ik_rating'] or final_fields[col] == 'NULL':
                                    # Only update if not already set by value-based extraction 
                                    escaped_val = val.replace("'", "''")
                                    final_fields[col] = f"'{escaped_val}'"
                                matched = True
                                break
                        
                        if not matched:
                            extra_specs[key] = val

                    stmt = f"INSERT INTO hardware (model_name, operate_temperature, input_power, ip_rating, ik_rating, interface, extra_specs) VALUES ('{model_name}', {final_fields['operate_temperature']}, {final_fields['input_power']}, {final_fields['ip_rating']}, {final_fields['ik_rating']}, {final_fields['interface']}, '{json.dumps(extra_specs)}');"
                    sql_statements.append(stmt)
                    
    # Keep generated SQL separate from the source data.
    with open("backend/db_scripts/insert_hardware.sql", "w") as out_f:
        out_f.write("\n".join(sql_statements))
    print(f"Generated {len(sql_statements)} INSERT statements in backend/db_scripts/insert_hardware.sql")

if __name__ == "__main__":
    process_files()
