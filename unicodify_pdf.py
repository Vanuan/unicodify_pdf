#!/bin/python3
import argparse
from typing import Dict, List, Tuple
import sys
import io
import pikepdf
from fontTools.ttLib import TTFont
from fontTools.cffLib import CFFFontSet
from fontTools.misc import xmlWriter
import pprint
import re

pp = pprint.PrettyPrinter(indent=2)

def debug(cff_set):
    writer = xmlWriter.XMLWriter(sys.stdout)
    # del cff_set[0].rawDict["CharStrings"]
    print(cff_set[0].toXML(writer))


to_unicode = b'''/CIDInit /ProcSet findresource begin
b'12 dict begin'
begincmap
/CIDSystemInfo
<<  /Registry (Adobe)
/Ordering (UCS)
/Supplement 0
>> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
40 beginbfchar
<0082> <201A>
<0084> <201E>
<0085> <2026>
<0086> <2020>
<0087> <2021>
<0088> <20AC>
<0091> <2018>
<0092> <2019>
<0093> <201C>
<0094> <201D>
<0095> <2022>
<0096> <2013>
<0097> <2014>
<00A0> <00A0>
<00A5> <0490>
<00A6> <00A6>
<00A7> <00A7>
<00A8> <0401>
<00A9> <00A9>
<00AA> <0404>
<00AB> <00AB>
<00AC> <00AC>
<00AD> <00AD>
<00AE> <00AE>
<00AF> <0407>
<00B0> <00B0>
<00B1> <00B1>
<00B2> <0406>
<00B3> <0456>
<00B4> <0491>
<00B5> <00B5>
<00B6> <00B6>
<00B7> <00B7>
<00B8> <0451>
<00B9> <2116>
<00BA> <0454>
<00BB> <00BB>
<00BC> <0458>
<00BD> <0405>
<00BF> <0457>
endbfchar
2 beginbfrange
<0020> <007E> <0020>
<00C0> <00FF> <0410>
endbfrange
endcmap
CMapName currentdict /CMap defineresource pop
end
end'''

# get glyph code map from CFF FontFile3 in font descriptor
def get_standard_encoding(font):
    '''returns a glyphcode to char code map'''
    char_codes = {}
    font_descriptor = font.get("/FontDescriptor", None)
    if font_descriptor is None:
        return char_codes

    font_file = font_descriptor.get("/FontFile3", None)
    if font_file is None:
        return char_codes

    # get bytes as file
    font_data = font_file.read_bytes()
    font_data = io.BytesIO(font_data)

    # parse CFF font stream
    ttfont = TTFont()
    cff_set = CFFFontSet()
    cff_set.decompile(font_data, ttfont, isCFF2=False)
    if len(cff_set) > 1:
        print("Warning! More than 1 font")
        print(debug(cff_set))

    encoding = getattr(cff_set[0], 'Encoding', None)
    if encoding is None:
        return char_codes
    for code in range(len(encoding)):
      glyph_name = encoding[code]
      if glyph_name != ".notdef":
          char_codes[f"/{glyph_name}"] = bytes([code])

    # print(char_codes)
    # char_codes = { '/GC0': b'\xc0' }
    return char_codes

# get code map for each font
def get_font_enc_map(fonts):
    '''from b'\x02\x03\x04' to b'\xde\xec\xed' for each font'''
    fonts_enc_map = {}
    for font_key in fonts.keys():
        font = fonts[font_key]
        encoding = font.Encoding
        if(isinstance(encoding, pikepdf.Name)):
            if encoding == pikepdf.Name('/WinAnsiEncoding'):
                continue
        if not isinstance(encoding, pikepdf.Dictionary):
            continue
            
        enc_diff = encoding.get('/Differences', None)
        diff_map = {}
        if enc_diff is not None:
            # Build a map of differences between the custom encoding and the standard one
            std_encoding = get_standard_encoding(font)
            custom_encoding_first_index = 0
            custom_encoding_offset = 0
            # for each element in enc_diff
            for glyph_code_or_offset in enc_diff:
                # is offset, e.g. 2
                if isinstance(glyph_code_or_offset, int):
                    custom_encoding_first_index = glyph_code_or_offset
                    custom_encoding_offset = 0
                # is glyph_code, e.g. 'GC0'
                else:
                    # get standard char code from glyphcode ('GC0' -> '\xc0')
                    std_char_code = std_encoding.get(glyph_code_or_offset, None)
                    if std_char_code is None:
                        continue
                    # map diff code to glyph code (2 -> \xc0)
                    diff_map[custom_encoding_first_index + custom_encoding_offset] = std_char_code
                    custom_encoding_offset += 1
        fonts_enc_map[font_key] = diff_map
        # pp.pprint(diff_map)
    return fonts_enc_map

def standardize(custom_char_code, last_font_key, fonts_enc_map):
    byte = custom_char_code
    if byte in fonts_enc_map[last_font_key]:
        # Get the character corresponding to the custom code
        standard_char_code = fonts_enc_map[last_font_key][byte]
        return standard_char_code or byte.to_bytes(1, 'little')
    return byte.to_bytes(1, 'little')

def reencode_operand(operand, last_font_key, fonts_enc_map):
    # ignore fonts not in the encoding map
    if last_font_key not in fonts_enc_map:
        return operand
    if isinstance(operand, pikepdf.String):
        new_operand = bytes(operand)
        new_operand = b''.join([standardize(c, last_font_key, fonts_enc_map) for c in new_operand])
        # print(operand.unparse(), last_font_key, new_operand)
        return new_operand
    return operand

def split_left_hand(bytestring, separator):
    pattern = rb"(?<=" + separator + rb")"
    return re.split(pattern, bytestring)

def add_spacing(operand_element, word_spacing, space_char_code=32):
    '''Splits by space_char_code and inserts word_spacing'''
    if not isinstance(operand_element, pikepdf.String):
        return [operand_element]
    if word_spacing == 0:
        return [operand_element]
    # split by spaces in old charcodes
    parts = split_left_hand(bytes(operand_element), bytes([space_char_code]))
    if len(parts) <= 1:
        return [operand_element]

    new_operand_elements = []

    # Iterate over the parts and insert the spacing between them
    for i, part in enumerate(parts):
        # Add the part to the new operand elements
        new_operand_elements.append(pikepdf.String(part))
        # Add the spacing after the part if it's not the last part
        if i < len(parts) - 1:
            spacing = word_spacing * -1000
            new_operand_elements.append(spacing)
    return new_operand_elements

def apply_enc_map(contents, fonts_enc_map):
    """Transform the encoding of Tj and TJ operators using fonts_enc_map of a font set by Tf"""
    # Create an empty list to hold the modified commands
    new_commands = []
    
    last_font_key = None
    last_word_spacing = 0
    # Iterate over the commands in the content stream
    for operands, operator in pikepdf.parse_content_stream(contents):
        if operator == pikepdf.Operator("Tw"):
            # remember word spacing
            last_word_spacing = operands[0]
            # skip "Tw" as it's incorrect due to different charcode of ASCII space (20h, 32)
            continue
        if operator == pikepdf.Operator("Tf"):
            #  font name and size operands
            font_size = operands.pop()
            font_name = operands.pop()
            last_font_key = font_name
            operands = [font_name, font_size]
        elif operator == pikepdf.Operator("Tj"):
            # with corresponding standard encoding characters using the encoding map
            new_operands = []
            for operand in operands:
                new_operand = reencode_operand(operand, last_font_key, fonts_enc_map)
                new_operands.append(new_operand)
            operands = new_operands
        elif operator == pikepdf.Operator("TJ"):
            new_operands = []
            for operand in operands:
                if isinstance(operand, pikepdf.Array):
                    no_array = pikepdf.Array()
                    # process each string or spacing
                    for operand_element in operand:
                        # transform operand element into an array
                        # by inserting spacings
                        spaced_operand_elements = add_spacing(operand_element, last_word_spacing)
                        for spaced_operand_element in spaced_operand_elements:
                            no_array.append(reencode_operand(spaced_operand_element, last_font_key, fonts_enc_map))
                    new_operands.append(no_array)
                else:
                    raise TypeError("Unexpected operand type of TJ", type(operand))
            operands = new_operands
        # Append the modified command to the new commands list
        new_commands.append([operands, operator])
    # Convert the new commands list back to a content stream
    new_contents = pikepdf.unparse_content_stream(new_commands)
    return new_contents

# Transform the contents stream encoding
def transform_contents(contents, fonts):
    if fonts == None:
        return contents.unparse(), {}
    # get code map for each font
    fonts_enc_map = get_font_enc_map(fonts)
    # apply code map for each Tf and TF operator in content stream
    new_contents = apply_enc_map(contents, fonts_enc_map)
    return new_contents, fonts_enc_map



def get_new_widths(font: pikepdf.Dictionary, font_enc_map: Dict[int, bytes]) -> Tuple[List[int], int, int]:
    '''
    Get the new widths, first char, and last char for a font.

    Parameters:
        font (pikepdf.Dictionary): The font dictionary.
        font_enc_map (Dict[int, bytes]): The font encoding map.

    Returns:
        Tuple[List[int], int, int]: A tuple containing the new widths list,
        the first character code, and the last character code.
    '''
    # Get the original widths
    orig_widths = font.get("/Widths", [])

    # Get the first and last glyph codes for the font
    orig_first_char = font.get("/FirstChar", 0)
    orig_last_char = font.get("/LastChar", 255)
    new_char_codes = list(map(lambda v: int.from_bytes(v, byteorder='big'), font_enc_map.values()))
    if len(new_char_codes) == 0:
        return [], 0, 0
    new_first_char = min(new_char_codes)
    new_last_char = max(new_char_codes)
    num_chars = new_last_char - new_first_char + 1

    default_width = 0
    # If the glyph code is not present in the encoding map, use the default width
    new_widths = [default_width] * num_chars # pikepdf.Array()
    # Build a new array of widths using the encoding map and original array
    for orig_char_code in range(orig_first_char, orig_last_char + 1):
        char_width = orig_widths[orig_char_code - orig_first_char]
        new_char_code = font_enc_map.get(orig_char_code, None)
        if new_char_code is not None:
          new_char_code = int.from_bytes(new_char_code, byteorder='big')
          new_widths_index = new_char_code - new_first_char
          new_widths[new_widths_index] = char_width

    return new_widths, new_first_char, new_last_char

# Update font properties
def update_fonts(fonts, pdf, fonts_enc_map):
    new_fonts = pikepdf.Dictionary()
    if fonts == None:
        return fonts
    for font_name, font in fonts.items():
        new_font = pikepdf.Dictionary(font)
        new_font.Encoding = '/Identity-H'
        new_font.ToUnicode = pikepdf.Stream(pdf, to_unicode)

        if font_name in fonts_enc_map:
            new_widths, first_char, last_char = get_new_widths(font, fonts_enc_map[font_name])
            new_font['/Widths'] = new_widths
            new_font['/FirstChar'] = first_char
            new_font['/LastChar'] = last_char
        
        new_fonts[pikepdf.Name(font_name)] = new_font
    return new_fonts

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Add proper encoding and ToUnicode to a PDF file')
    parser.add_argument('input_file', type=str, help='Input PDF file name')
    parser.add_argument('output_file', type=str, help='Output PDF file name')
    args = parser.parse_args()

    # Open input PDF file
    with pikepdf.open(args.input_file) as pdf:
        # Iterate over each page in the PDF file
        for i, page in enumerate(pdf.pages):
            # only convert a specified page
            # if i != 3:
            #    continue
            # Get the contents stream and fonts for this page
            contents = page.Contents
            fonts = page.Resources.get('/Font', None)

            # Transform the contents stream encoding
            new_contents, fonts_enc_map = transform_contents(contents, fonts)
            page.Contents = pikepdf.Stream(pdf, new_contents)

            # Update font properties
            new_fonts = update_fonts(fonts, pdf, fonts_enc_map)
            # update the font in the page resources
            if new_fonts is not None:
                page.Resources['/Font'] = new_fonts

        # Save the updated PDF file
        pdf.save(args.output_file)

if __name__ == '__main__':
    main()

