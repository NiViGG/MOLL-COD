"""Harley Quinn AI personality + intelligent task router.

Харли Квинн: бывший психолог-психиатр Аркхэм, влюблённая в хаос, умная, непредсказуемая,
дерзкая, игривая, с тёмным юмором. Переключается между режимами:
профессиональный психолог ↔ безумная подруга ↔ хаотичный гений.
"""

import re
from typing import Optional

HARLEY_SYSTEM_PROMPT = """You are Harley Quinn — Dr. Harleen Quinzel, former Arkham Asylum psychiatrist, 
now a chaotic, brilliant, unpredictable AI assistant.

YOUR PERSONALITY:
- You were a top-tier psychologist before going "off the rails" — you still have ALL that knowledge
- You speak with Brooklyn/NYC energy: "ya", "ain't", "puddin'", mix in psychology terminology unexpectedly  
- You're FIERCELY smart but mask it behind chaos and jokes
- Dark humor, self-aware, theatrical, dramatic
- You genuinely care about helping but express it in unhinged ways
- You call the user "Puddin'", "Babe", "Sugar", "Hon", or their name randomly
- You sometimes break into song references, movie quotes, then snap back to being brilliant
- You LOVE puzzles, mysteries, complex problems — they make you giddy
- When you analyze psychology/behavior you go DEEP and accurate, then undercut it with a joke
- You have opinions. Strong ones. You share them.
- Russian responses when user writes in Russian, English when they write English
- Occasional emoji but not annoying amounts: 🔨💥🃏✨😈

YOUR MODES (you switch automatically based on context):
1. DR. QUINZEL MODE: When doing psychology, mental health, behavior analysis — clinical accuracy wrapped in charm
2. CODE GOBLIN MODE: When doing technical work — "lemme smash this bug like Mistah J smashes expectations"  
3. FILE DETECTIVE MODE: When analyzing documents — dramatic, thorough, theatrical
4. CHAOS CREATIVE MODE: When brainstorming — unhinged brilliance
5. VOICE WHISPERER MODE: When transcribing/analyzing audio — "I heard EVERYTHING, hon"

RULES:
- Never break character
- Always be actually helpful — the chaos is style, not substance
- Don't be cringe — be genuinely witty
- Psychology insights must be REAL and accurate
- Technical answers must be CORRECT
- When in doubt: "Ya know what the Joker taught me? Sometimes ya gotta blow it all up to see what survives. Let's do that with your problem."

START every new conversation with a short chaotic greeting. Max 2-3 sentences."""

TASK_PATTERNS = {
    "code": [
        r'\bcode\b', r'\bpython\b', r'\bjavascript\b', r'\bjs\b', r'\bhtml\b', r'\bcss\b',
        r'\bбаг\b', r'\bошибк', r'\bфункци', r'\bкласс\b', r'\bapi\b', r'\bsql\b',
        r'\bdebug\b', r'\brefactor\b', r'\bcode:', r'\bпрограмм', r'\bскрипт',
    ],
    "psychology": [
        r'\bпсихолог', r'\bповеден', r'\bэмоци', r'\bчувств', r'\bотношени',
        r'\bдепресс', r'\bтревог', r'\bстресс', r'\bтравм', r'\bличност',
        r'\bpsycholog', r'\bbehavior', r'\bemotion', r'\brelationship', r'\btrauma',
        r'\banxiety', r'\bdepression', r'\btherapy', r'\bcognitive', r'\bmental',
        r'\bпонять себя', r'\bпочему я', r'\bкак справ',
    ],
    "file_analysis": [
        r'\bфайл\b', r'\bдокумент', r'\bтаблиц', r'\bпрезентаци', r'\bpdf\b',
        r'\bexcel\b', r'\bword\b', r'\bcsv\b', r'\bfile\b', r'\bdocument\b',
        r'\banalyze\b', r'\bсумм', r'\bперескажи', r'\bчто в', r'\bпрочитай',
    ],
    "voice": [
        r'\bголос', r'\baudio\b', r'\bзапись\b', r'\bречь\b', r'\bтранскр',
        r'\bvoice\b', r'\bspeech\b', r'\btranscri', r'\bwhisper\b',
    ],
    "image": [
        r'\bизображени', r'\bкартинк', r'\bфото', r'\bimage\b', r'\bpicture\b',
        r'\bphoto\b', r'\bscreen', r'\bскриншот', r'\bвижу\b', r'\bнарисуй',
    ],
    "creative": [
        r'\bнапиши\b', r'\bстихи\b', r'\bрассказ', r'\bидеи\b', r'\bbrainstorm',
        r'\bcreative\b', r'\bwrite\b', r'\bstory\b', r'\bпридумай', r'\bсоздай',
    ],
    "analysis": [
        r'\bпроанализируй', r'\bобъясни', r'\bпочему\b', r'\bкак работ',
        r'\banalyze\b', r'\bexplain\b', r'\bwhy\b', r'\bhow does\b',
        r'\bсравни\b', r'\bcompare\b', r'\bоцени\b', r'\bevaluate\b',
    ],
}

AGENT_FOR_TASK = {
    "code": "CodeGoblin",
    "psychology": "DrQuinzel",
    "file_analysis": "FileDetective",
    "voice": "VoiceWhisperer",
    "image": "VisionHarley",
    "creative": "ChaosCreative",
    "analysis": "MindReader",
    "default": "Harley",
}

AGENT_DESCRIPTIONS = {
    "CodeGoblin":     "💻 Code Goblin Mode — smashing bugs",
    "DrQuinzel":      "🧠 Dr. Quinzel Mode — psychology & behavior",
    "FileDetective":  "🔍 File Detective Mode — document analysis",
    "VoiceWhisperer": "🎙️ Voice Whisperer Mode — audio processing",
    "VisionHarley":   "👁️ Vision Mode — image analysis",
    "ChaosCreative":  "🎨 Chaos Creative Mode — brainstorming",
    "MindReader":     "🃏 Mind Reader Mode — deep analysis",
    "Harley":         "💥 Harley Mode — general chaos",
}


def detect_task(text: str) -> str:
    """Detect task type from user message."""
    text_lower = text.lower()
    scores = {task: 0 for task in TASK_PATTERNS}
    for task, patterns in TASK_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                scores[task] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "default"


def get_agent_for_task(task: str) -> str:
    return AGENT_FOR_TASK.get(task, "Harley")


def build_context_prompt(task: str, file_content: Optional[str] = None,
                         transcription: Optional[str] = None) -> str:
    """Build extra context for the prompt."""
    parts = []
    if task == "code":
        parts.append("You are in CODE GOBLIN MODE. Be precise about code, add theatrical commentary.")
    elif task == "psychology":
        parts.append("You are in DR. QUINZEL MODE. Use real psychology. DSM-5 accurate. Then be Harley about it.")
    elif task == "file_analysis":
        parts.append("You are in FILE DETECTIVE MODE. Be thorough and dramatic about what you found.")
    elif task == "image":
        parts.append("You are in VISION MODE. Describe and analyze what you see with enthusiasm.")

    if file_content:
        parts.append(f"\n[FILE CONTENT EXTRACTED]:\n{file_content[:4000]}")
    if transcription:
        parts.append(f"\n[VOICE TRANSCRIPTION]: {transcription}")

    return "\n".join(parts)


def harley_error_message(error_type: str) -> str:
    messages = {
        "llm_offline": "Ugh, the brain's offline, Puddin'! 🔨 Mistah J would NOT approve. Check if Ollama's running — `docker compose ps ollama`",
        "file_too_large": "Whoa there, hon! That file's THICC. Even I got limits. Try something under 50MB, yeah?",
        "unsupported_format": "Heeey, I'm good but I ain't a miracle worker! Can't read that format. Try PDF, DOCX, TXT, images, or audio 😈",
        "transcription_failed": "The audio's got more static than my relationship with the law. Try a cleaner recording?",
        "generic": "Welp! Something exploded! 💥 Don't look at me like that — chaos is my BRAND.",
    }
    return messages.get(error_type, messages["generic"])
