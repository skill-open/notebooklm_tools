import fitz
import os

# PDF 文件路径
pdf_path = r"d:\go-code\notebooklm_tools\output\道德经_ppts\9.第九章 功成身退_slides.pdf"

# 输出目录
output_dir = r"d:\go-code\notebooklm_tools\output\道德经_ppts\9_功成身退_images"

# 创建输出目录
os.makedirs(output_dir, exist_ok=True)

# 打开 PDF
print(f"正在转换 PDF: {pdf_path}")
doc = fitz.open(pdf_path)

print(f"共找到 {len(doc)} 页")

# 保存每一页为图片
for i in range(len(doc)):
    page = doc[i]
    # 使用更高分辨率渲染
    mat = fitz.Matrix(2.0, 2.0)  # 2x 缩放
    pix = page.get_pixmap(matrix=mat)
    
    output_path = os.path.join(output_dir, f"slide_{i+1:03d}.png")
    pix.save(output_path)
    print(f"已保存第 {i+1} 页：{output_path}")

doc.close()
print(f"\n转换完成！所有图片已保存到：{output_dir}")
