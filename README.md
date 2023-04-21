# Unicodify PDF

## Overview

This script converts a PDF file with embedded fonts that lack Unicode mapping
into a PDF file with properly encoded text.
This enables copy and search functionality that was previously uncommon
due to the limited Unicode support in PDFs of the early 2000s.

The script solves this problem by adding Unicode information to the embedded fonts and fixing some other issues.

## Background

Many PDF files were created in the early 2000s with embedded fonts with custom encoding, without Unicode mapping. This can make it difficult or impossible to searchor copy text from these PDF files.

Before Unicode became the industry standard for encoding text, PDF publishers used tools like Adobe PageMaker to create PDF files with embedded fonts. However, because of the limited Unicode support in PDFs of that era and to make PDF files as small as possible, these files don't have a Unicode mapping and only have custom encoding, which means that text in those PDF files can not be searched or copied and pasted. This poses a significant challenge for anyone who needs to extract text from these PDF files for analysis or translation.

## Usage
To use the script, you can run it from the command line with the following arguments:

```
python unicodify_pdf.py input.pdf output.pdf
```

Where `input.pdf` is the path to PDF file to unicodify and `output.pdf` is the path of the resulting unicodified PDF file.

## Requirements

The script requires Python 3.6 or later, as well as some libraries, which can be installed via pip:

```bash
pip install pikepdf fonttools
```

## How the script works

The script takes an input PDF file, extracts its text content, and then re-encodes the text using the standard encoding while providing Unicode mapping for each glyph.
Specifically, it uses pikepdf to load and modify the PDF file, and fonttools to extract the font information. It then modifies the PDF file by replacing the custom-encoded text with standard ANSI encoded text and provided the standard Unicode mapping.

The script also adds the word spacing to the text in the PDF file, because with custom encoding, PDF might not use a proper code for the space character. This is done by inserting spacing after the character with the code '\x20'.

To find the correspondence between the custom encoding and the standard ANSI encoding, the iterating over each embedded font, analyzes the font encoding and builds glyph-to-character mappings.


## Limitations

Currently only supports the Cyrillic (Windows-1251) mapping.

The script may not work for all PDF files, especially those with complex font encoding or other non-standard features.

Additionally, the script may increase the file size of the output PDF file, depending on the size of the embedded fonts and the amount of word spacing added.

Finally, because the script touches the input PDF file, it is recommended to create a backup copy of the input file before running the script.

## License

The `unicodify_pdf.py` script is released under the MIT License.
