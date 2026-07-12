# Courseware index

The included index covers 7 PDFs, 737 pages and 726 non-empty page-aware chunks.

To rebuild after replacing a lecture PDF:

1. Run `pdftotext -layout source.pdf courseware-source/text/<matching-name>.txt`.
2. Keep the source mapping in `scripts/build-courseware-index.mjs` aligned with the PDF slug in `public/courseware/`.
3. Run `node scripts/build-courseware-index.mjs`.
4. Run the retrieval and full test suites.
5. Spot-check citations against rendered PDF pages before publishing.

The generated JSON is committed intentionally so the worker does not need filesystem access or a PDF parser at runtime.
