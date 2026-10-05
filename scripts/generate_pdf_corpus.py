from fpdf import FPDF

pdf = FPDF()
pdf.add_page()
pdf.set_font("Helvetica", size=16)
pdf.multi_cell(w=pdf.epw, h=10, text="IntelligenceOS Product Architecture and Platform Specification", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(8)

pdf.set_font("Helvetica", size=10)
with open("test_corpus/IntelligenceOS_Product_Architecture.md", "r", encoding="utf-8") as f:
    content = f.read()

for line in content.splitlines():
    if line.startswith("#"):
        pdf.set_font("Helvetica", "B", 12)
        pdf.ln(4)
        clean = line.replace("#", "").strip()
        pdf.multi_cell(w=pdf.epw, h=7, text=clean, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
    elif line.strip():
        sanitized = line.encode("ascii", "replace").decode("ascii")
        pdf.multi_cell(w=pdf.epw, h=6, text=sanitized, new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.ln(2)

pdf.output("test_corpus/IntelligenceOS_Product_Architecture.pdf")
print("PDF generated successfully: test_corpus/IntelligenceOS_Product_Architecture.pdf")
