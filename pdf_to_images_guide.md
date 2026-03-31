# PDF 转图片工具使用指南

## 使用的工具

**PyMuPDF (fitz)** - 一个高性能的 PDF 处理库

- **库名称**: PyMuPDF
- **导入名**: `fitz`
- **版本**: 1.27.1
- **优势**: 
  - 无需安装额外的依赖（如 poppler）
  - 渲染质量高
  - 支持自定义分辨率
  - 处理速度快

## 安装方法

```bash
pip install PyMuPDF
```

## 使用方法

### 基本代码模板

```python
import fitz
import os

# PDF 文件路径
pdf_path = r"path/to/your/document.pdf"

# 输出目录
output_dir = r"path/to/output/images"

# 创建输出目录
os.makedirs(output_dir, exist_ok=True)

# 打开 PDF
doc = fitz.open(pdf_path)

print(f"共找到 {len(doc)} 页")

# 保存每一页为图片
for i in range(len(doc)):
    page = doc[i]
    # 使用更高分辨率渲染
    mat = fitz.Matrix(2.0, 2.0)  # 2x 缩放
    pix = page.get_pixmap(matrix=mat)
    
    output_path = os.path.join(output_dir, f"page_{i+1:03d}.png")
    pix.save(output_path)
    print(f"已保存第 {i+1} 页：{output_path}")

doc.close()
print(f"\n转换完成！所有图片已保存到：{output_dir}")
```

### 参数说明

#### 分辨率设置

```python
# 1x 原始分辨率
mat = fitz.Matrix(1.0, 1.0)

# 2x 分辨率（推荐，高质量）
mat = fitz.Matrix(2.0, 2.0)

# 3x 超高分辨率
mat = fitz.Matrix(3.0, 3.0)

# 自定义宽高缩放
mat = fitz.Matrix(1.5, 2.0)  # 宽度 1.5x, 高度 2x
```

#### 输出格式

```python
# PNG（推荐，无损压缩）
pix.save("output.png")

# JPG（有损压缩，文件更小）
pix.save("output.jpg")

# 其他支持的格式：JPEG, PNG, PNM, PPM, TGA, GIF, TIFF, WEBP
```

### 完整示例脚本

项目中的脚本位置：`convert_pdf_to_images.py`

运行方式：
```bash
python convert_pdf_to_images.py
```

## 输出示例

```
正在转换 PDF: d:\go-code\notebooklm_tools\output\道德经_ppts\1.第一章 道可道非常道_slides.pdf
共找到 9 页
已保存第 1 页：d:\go-code\notebooklm_tools\output\道德经_ppts\slides_images\slide_001.png
已保存第 2 页：d:\go-code\notebooklm_tools\output\道德经_ppts\slides_images\slide_002.png
...
转换完成！所有图片已保存到：d:\go-code\notebooklm_tools\output\道德经_ppts\slides_images
```

## 其他方法对比

### 方法 1：pdf2image（需要 poppler）

```python
from pdf2image import convert_from_path

images = convert_from_path('document.pdf', dpi=300)
for i, image in enumerate(images, 1):
    image.save(f'page_{i}.png', 'PNG')
```

**缺点**: 
- 需要安装 poppler 工具
- Windows 上配置复杂

### 方法 2：PyMuPDF（推荐）✅

```python
import fitz

doc = fitz.open('document.pdf')
page = doc[0]
pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
pix.save('page.png')
```

**优点**:
- 无需额外依赖
- 跨平台支持好
- 性能优秀
- API 简洁

## 常见问题

### Q: 图片太模糊怎么办？
A: 增加缩放比例，例如：
```python
mat = fitz.Matrix(3.0, 3.0)  # 3x 缩放
```

### Q: 如何只转换特定页面？
A: 修改循环范围：
```python
# 只转换第 1-5 页
for i in range(0, 5):
    page = doc[i]
    # ...
```

### Q: 如何批量转换多个 PDF？
A: 使用循环：
```python
import glob

for pdf_file in glob.glob("*.pdf"):
    doc = fitz.open(pdf_file)
    # 处理每个 PDF
```

## 参考资源

- PyMuPDF 官方文档：https://pymupdf.readthedocs.io/
- PyMuPDF GitHub: https://github.com/pymupdf/PyMuPDF
- 项目脚本：`convert_pdf_to_images.py`
