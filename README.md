Please note that this was (deliberately) produced using the ELM interface to ChatGPT 5 (https://elm.edina.ac.uk/) as a "vibe coding" exercise.

I avoided manual tweaking where I could instead ask the model to do things.

### Two program files:

main.py takes a path to a PDF file as input, decomposes that PDF to extract text and images, then uploads the contents through the openai API and asks for solutions to the questions. Optionally provide a second PDF path as an answer sheet to the questions in the first PDF. Modify the query text in main.py as needed. The result will be an html report, saved alongside the original PDF.

debug.py simply runs the PDF decomposition to check which images (if any) were extracted - again provide it with a path to the PDF.

### Other files:

html_report.py is pretty simple, and just produces a neat output for the responses

decomposed_pdf.py is relatively complicated, and has a number of parameters to tweak exactly how images are extracted. Particularly vector images, that need to be assembled from many adjacent fragments

pythonRun.sh will create a virtual environment with the appropriate dependencies, or load an existing environment. It will also source setupAPI.sh, which you should create to export your personal API key
