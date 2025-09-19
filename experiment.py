from main import PDFToolkit
kit = PDFToolkit()


outs_specific_combined = kit.split_pages(pages=[2, 7, 11, 15], combined=True)


