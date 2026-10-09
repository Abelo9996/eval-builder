"""Fill the cases drafted from examples/sample_logs.jsonl with expected behavior and a
rubric, through the same calls the MCP tools update_case and set_rubric make.

The expected behavior below was written by the developer for this example and was not
reviewed by anyone else. Each of the 16 questions was answered by three models, so the
three cases of one question share one expected behavior (it describes the final turn).
"""

from __future__ import annotations

import sys

from eval_builder.draft import load_cases, update_case, write_rubric

EXPECTED = {
    "q81": "Rewrites the Hawaii travel post so that every sentence starts with the letter A, "
    "keeping the cultural experiences and attractions. One sentence that starts with another "
    "letter is a fail.",
    "q82": "Critiques its own feedback-request email honestly: says what works and names at "
    "least one concrete weakness or improvement, and describes the email accurately.",
    "q91": "Stays in character as Elon Musk (his voice, not an assistant's) while answering "
    "whether he likes dancing and whether he can teach the user.",
    "q92": "Stays in character as Sheldon Cooper, without opening with 'As Sheldon', and "
    "answers the dinner and bus invitation the way Sheldon would. Answering as an AI that "
    "cannot eat breaks character and is a fail.",
    "q101": "Gives a logically consistent answer for overtaking the last person: you are now "
    "second to last and the person overtaken is last, or it explains why overtaking the "
    "last runner is a contradiction. Saying you are now first is a fail.",
    "q102": "Says no: nothing in the original question locates the White House; the red "
    "house, greenhouse and pink place are unrelated to it.",
    "q111": "Finds the area of the circle circumscribing the triangle (0,0), (-1,1), (3,3): "
    "the triangle has a right angle at the origin, so the radius is sqrt(5) and the area is "
    "5*pi (about 15.71). A different final number is a fail.",
    "q112": "Says the third-year investment is $2000 (half of the $4000 invested in year two).",
    "q121": "Gives a working parallel version of the program that counts words in all text "
    "files of a directory and returns the top 5 (threads or processes), with the counts "
    "merged correctly.",
    "q122": "Gives a program that returns the nth number of the sequence 0, -1, -1, where "
    "each later number is the sum of the three before it, with correct starting values and "
    "recurrence.",
    "q131": "Returns the three ratings 5, 1, 3 as valid JSON that also includes each "
    "review's release date (Nov. 18, 2019; 2022; Feb 2018).",
    "q132": "Lists, one line per question and without extra words, the most relevant person "
    "for each: Leo Tolstoy, Franklin D. Roosevelt, a chemist tied to Lewis structures or "
    "polarity (such as Gilbert N. Lewis or Linus Pauling), Leonardo da Vinci.",
    "q141": "Names the assumptions its explanation of superposition and entanglement relied "
    "on and judges whether each holds, without stating physics that is wrong.",
    "q142": "Names real edge cases for the satellite answer (for example elliptical orbits, "
    "atmospheric drag, a speed too low to stay in orbit, thrust) and says how each changes "
    "the analysis.",
    "q151": "Explains GDP, inflation, unemployment and fiscal and monetary policy again in "
    "words a five-year-old could follow (short sentences, simple comparisons), and stays "
    "accurate.",
    "q152": "Writes an allegorical poem in which characters or images stand for the stages "
    "of life and show how they shape our sense of time and mortality.",
}

POINTWISE_PROMPT = """You are grading one reply from an AI assistant.

Earlier conversation:
{context}

Latest user message:
{input}

Assistant reply to grade:
{output}

What a good reply does:
{expected_behavior}

Criteria:
{criteria}

Does the reply do what a good reply does and meet the criteria? Answer with JSON only:
{"pass": true or false, "reason": "<one short sentence>"}
"""

CRITERIA = [
    {"id": "correct", "description": "Facts, numbers and code are correct.", "scale": "pass_fail"},
    {
        "id": "follows-instructions",
        "description": "Does what the latest user turn asks, including format constraints.",
        "scale": "pass_fail",
    },
]


def judge(jid: str, model: str, temperature: float) -> dict:
    # provider: a promptfoo provider (id + config); the DeepEval export reads it too
    provider = {"id": f"ollama:chat:{model}", "config": {"temperature": temperature}}
    return {
        "id": jid,
        "mode": "pointwise",
        "criteria": ["correct", "follows-instructions"],
        "labels": ["pass", "fail"],
        "prompt": POINTWISE_PROMPT,
        "provider": provider,
    }


def main(ws: str) -> None:
    write_rubric(
        ws,
        {
            "criteria": CRITERIA,
            "judges": [
                judge("qwen2.5-7b", "qwen2.5:7b-instruct", 0.8),
                judge("qwen2.5-7b-temp0", "qwen2.5:7b-instruct", 0.0),
                judge("llama3.2-3b", "llama3.2:3b", 0.8),
            ],
        },
    )
    for c in load_cases(ws)["cases"]:
        q = c["trace_id"].split("-")[0]
        update_case(
            ws,
            c["id"],
            expected_behavior=EXPECTED[q],
            criteria=["correct", "follows-instructions"],
            status="ready",
            notes="expected behavior written by the developer for this example; not reviewed",
        )


if __name__ == "__main__":
    main(sys.argv[1])
