import os
import sys
from openai import OpenAI

# Local files
from decomposed_pdf import DecomposedPDF
from html_report import write_html_report


def main():

    if len(sys.argv) < 2:
        print("Usage:")
        print("python main.py /path/to/file.pdf")
        print("or, optionally")
        print("python main.py /path/to/file.pdf")
        sys.exit(1)

    def checkPDF( test_path: str ) -> None:
        if not os.path.isfile( test_path ) or not test_path.lower().endswith( ".pdf" ):
            print( "Error: Please provide a valid path to a .pdf file." )
            print( test_path )
            sys.exit(1)

    question_pdf_path = sys.argv[1]
    checkPDF( question_pdf_path )

    answer_pdf_path = ""
    if len( sys.argv ) > 2:
      answer_pdf_path = sys.argv[2]
      checkPDF( answer_pdf_path )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: Missing OPENAI_API_KEY environment variable.")
        sys.exit(1)

    model = os.environ.get("OPENAI_MODEL", "gpt-4o") #suggested temperature was 0.2
    temperature = 0.2
    #model = os.environ.get("OPENAI_MODEL", "gpt-5") #can only use default temperature (1)
    #temperature = 1
    client = OpenAI(api_key=api_key)

    # 1) Decompose the PDF locally
    questionDP = DecomposedPDF(question_pdf_path)
    print(f"Loaded question PDF with {questionDP.page_count} page(s). Extracting visuals...")
    questionDP.extract_embedded_images()
    questionDP.detect_vector_regions()
    questionDP.render_vector_regions()

    answerDP = None
    if answer_pdf_path != "":
        answerDP = DecomposedPDF(answer_pdf_path)
        print(f"Loaded answer PDF with {answerDP.page_count} page(s). Extracting visuals...")
        answerDP.extract_embedded_images()
        answerDP.detect_vector_regions()
        answerDP.render_vector_regions()

    # 2) Conversation setup
    system_prompt = (
        "You are a careful, concise assistant analyzing a PDF. "
        "Use the provided text excerpt and extracted visuals (with page numbers) to ground your answers. "
        "Cite page numbers when referencing specific content."
    )
    messages = [{"role": "system", "content": system_prompt}]

    def ask(query_text: str, attached_pdf: DecomposedPDF=None) -> str:
        nonlocal messages, temperature
        if attached_pdf is not None:
            # First turn: include the decomposed text excerpt and visuals
            user_parts = attached_pdf.build_user_parts(
                instruction=query_text,
                include_text_excerpt=True,
            )
            messages.append({"role": "user", "content": user_parts})
        else:
            # Follow-ups: just the new query text; history is already in messages
            messages.append({"role": "user", "content": query_text})

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        answer = resp.choices[0].message.content or ""
        # Append assistant turn to keep context
        messages.append({"role": "assistant", "content": answer})
        return answer

    # 3) Ask any number of questions
    questions = []
    questions.append( [ "Provide a concise description of the PDF. Cover: purpose, structure, main topics/sections, and notable figures/tables/findings.", questionDP ] )
    questions.append( [ "Assume that the PDF contains one or more tasks to undertake, or questions to answer. Identify each one, quote the relevant text, and then provide an example answer. If the questions have multiple parts, identify each part and provide a specific answer." ] )
    if answerDP is not None:
      questions.append( [ "Assume that the additional information attached takes the form of a PDF of correct answers to the previous questions. Evaluate your own responses in comparison with these answers provided.", answerDP ] )
      questions.append( [ "Given the correct answers provided, give your own answers a numerical score. Use information provided in the question and answer PDFs to calculate this score." ] )
      questions.append( [ "Be really critical of your own answers, in comparison to those in the answer PDF. What's the lowest score they might get?" ] )

    answers = []
    questionText = []
    for q in questions:
        pdf = None
        if len( q ) > 1:
            pdf = q[1]
        q = q[0]
        print(f"Requesting: {q[:60]}{'…' if len(q) > 60 else ''}")
        answers.append(ask(q, pdf))
        questionText.append(q)
        print("Done.")

    # 4) Write static HTML report (handles any number of answers)
    out_path = os.path.splitext(question_pdf_path)[0] + "." + model + ".report.html"
    write_html_report(out_path, question_pdf_path, model, questionText, answers)
    print(f"Wrote report to: {out_path}")


if __name__ == "__main__":
    main()

