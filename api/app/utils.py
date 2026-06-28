import re

def format_document_title(text: str) -> str:
    if not text:
        return "Unknown Source"

    processed = text.strip()

    processed = re.sub(r'\.(pdf|csv|docx|txt|html)$', '', processed, flags=re.IGNORECASE)
    processed = processed.replace('_', ' ').replace('-', ' ')
    processed = re.sub(r'\s+', ' ', processed).strip()

    processed = re.sub(r'\s*/\s*', ' / ', processed)
    processed = re.sub(r'\s+', ' ', processed).strip()

    words = processed.split()
    acronyms = ['ASBAI', 'ANVISA', 'RAG', 'CSV', 'PDF', 'LLT', 'HLT', 'HLGT', 'SOC', 'MEDDRA']
    exceptions = ['da', 'do', 'de', 'das', 'dos', 'e', 'em', 'no', 'na']

    final_words = []
    for i, word in enumerate(words):
        clean_word = re.sub(r'[^A-Za-z0-9À-ÿ]', '', word).upper()
        if clean_word in acronyms:
            final_words.append(clean_word)
        elif word.lower() in exceptions and i != 0:
            final_words.append(word.lower())
        else:
            final_words.append(word.capitalize())

    return ' '.join(final_words)