"""
Excel Utilities - This module uses openpyxl to provide functionality to read and write
Microsoft Excel files.
"""

"""
@author: Chris Lamke
"""

import os
from openpyxl import Workbook # Using https://openpyxl.readthedocs.io/en/stable/tutorial.html for write to Excel
from openpyxl.styles import *
from openpyxl.utils import get_column_letter

""" XLSCellFormat class contains formatting details for Excel data """
class XLSCellFormat:
    font_name = 'Calibri'
    font_size = 11
    font_color = 'FF000000'
    is_bold = False
    is_italic = False
    #row_height = 0
    col_width = 20.0
    vert_align = 'top'
    horiz_align = 'left'
    wrap_text = True
    shrink_to_fit = False
    indent = 0
    #number_format = 'general'
    number_format = numbers.FORMAT_TEXT
    font = None
    #style = None
    alignment = None

    def __init__(self):
        pass

    def create_format(self):
        self.font = Font(name=self.font_name, size=self.font_size, color=self.font_color,
                         bold=self.is_bold, italic=self.is_italic)
        self.alignment = Alignment(horizontal=self.horiz_align, vertical=self.vert_align,
                                   wrap_text=self.wrap_text, shrink_to_fit=self.shrink_to_fit,
                                   indent=self.indent)

    def apply_format(self, ws, ws_row, ws_col):
        try:

            ws.cell(row=ws_row, column=ws_col).font = self.font
            ws.cell(row=ws_row, column=ws_col).alignment = self.alignment
            ws.cell(row=ws_row, column=ws_col).number_format = self.number_format
            #ws.dimensions.ColumnDimension[ws_col].width = self.col_width
            ws.column_dimensions[get_column_letter(ws_col)].width = self.col_width
        except (Exception) as ex:
            print("Problem during apply_format - " + str(ex))


""" XLSDoc class that creates, reads, and writes Excel files """
class XLSDoc:
    def __init__(self, excel_file_dir, excel_file_name):
        self.excel_file_name = excel_file_name
        self.excel_file_dir = excel_file_dir
        self.excel_file = os.path.join(excel_file_dir, excel_file_name)

        self.wb = Workbook()
        self.wb.active

        # BUGFIX: default_cell_format.create_format() was never called, so its
        # .font/.alignment stayed None. Any write_cell(...) call that omits the
        # format argument fell back to this uninitialized format, and
        # apply_format() would try to set ws.cell(...).font = None, which failed
        # silently (caught and only printed, not logged) inside apply_format's
        # own try/except. Each XLSDoc now gets its own initialized instance
        # instead of sharing the class-level default_cell_format object too.
        self.default_cell_format = XLSCellFormat()
        self.default_cell_format.create_format()

    def save_doc(self):
        self.wb.save(self.excel_file)

    def create_worksheet(self, sheet_name, index):
        self.wb.create_sheet(sheet_name, index) 
        return self.wb[sheet_name]

    def delete_worksheet(self, sheet_name):
        self.wb.remove(self.wb[sheet_name])

    def get_worksheet_by_name(self, sheet_name):
        return self.wb[sheet_name]

    def write_cell(self, ws, ws_row, ws_col, cell_value, format = None):
        ws.cell(row=ws_row, column=ws_col).value = cell_value
        if not format:
            format = self.default_cell_format
        
        format.apply_format(ws, ws_row, ws_col)

