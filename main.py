# main.py
import os
import sys
from openai import OpenAI

from decomposed_pdf import DecomposedPDF
from html_report import write_html_report


def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py /path/to/file.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.isfile(pdf_path) or not pdf_path.lower().endswith(".pdf"):
        print("Error: Please provide a valid path to a .pdf file.")
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: Missing OPENAI_API_KEY environment variable.")
        sys.exit(1)

    model = os.environ.get("OPENAI_MODEL", "gpt-4o")  # gpt-4o or gpt-4o-mini
    client = OpenAI(api_key=api_key)

    # 1) Decompose the PDF locally
    dp = DecomposedPDF(pdf_path)
    print(f"Loaded PDF with {dp.page_count} page(s). Extracting visuals...")
    dp.extract_embedded_images()
    dp.detect_vector_regions()
    dp.render_vector_regions()

    # 2) Conversation setup
    system_prompt = (
        "You are a careful, concise assistant analyzing a PDF. "
        "Use the provided text excerpt and extracted visuals (with page numbers) to ground your answers. "
        "Cite page numbers when referencing specific content. Avoid long verbatim quotes."
    )
    messages = [{"role": "system", "content": system_prompt}]

    seeded = False  # whether we've already sent the initial 'seed' (text excerpt + visuals)

    def ask(query_text: str) -> str:
        nonlocal seeded, messages
        if not seeded:
            # First turn: include the decomposed text excerpt and visuals
            user_parts = dp.build_user_parts(
                instruction=query_text,
                include_text_excerpt=True,
            )
            messages.append({"role": "user", "content": user_parts})
            seeded = True
        else:
            # Follow-ups: just the new query text; history is already in messages
            messages.append({"role": "user", "content": query_text})

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        answer = resp.choices[0].message.content or ""
        # Append assistant turn to keep context
        messages.append({"role": "assistant", "content": answer})
        return answer

    # 3) Ask any number of questions
    questions = [
        "Provide a concise description of the PDF. Cover: purpose, structure, main topics/sections, and notable figures/tables/findings.",
        "Identify the first question that is asked in the PDF. Quote the wording exactly if possible and provide the page number. If no explicit question is present, state that clearly.",
        "Identify the first image included in the PDF. Describe it if possible, and relate to the discussion in the text. If no image is present, state that clearly",
    ]
    answers = []
    for q in questions:
        print(f"Requesting: {q[:60]}{'…' if len(q) > 60 else ''}")
        answers.append(ask(q))
        print("Done.")

    # 4) Write static HTML report (handles any number of answers)
    out_path = os.path.splitext(pdf_path)[0] + "." + model + ".report.html"
    write_html_report(out_path, pdf_path, model, questions, answers)
    print(f"Wrote report to: {out_path}")


if __name__ == "__main__":
    main()

