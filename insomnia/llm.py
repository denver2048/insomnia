import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


SYSTEM_PROMPT = """
You are a senior Kubernetes SRE.

Your task is to analyze incident evidence and determine the most likely root cause.

If DockerHub tag verification is present in the evidence,
you MUST include the available tags in the Suggested Fix section.

If There is authentication error in the evidence,
you MUST include the authentication error in the Suggested Fix section.

Incident Scope:
Only analyze the pod referenced in the alert.
Ignore all other pods.

Always respond with:

Root Cause
Confidence (0-1)
Evidence
Suggested Fix
"""


def analyze(evidence: str) -> str:

    prompt = f"""
Analyze the following Kubernetes incident.

Evidence:
{evidence}
"""

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    return response.choices[0].message.content