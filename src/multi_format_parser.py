"""
Multi-format clinical document parser.
Handles: .docx, .pdf, .xlsx, .csv, .txt
Extracts tables and text for clinical MDT case processing.
"""

import json
import csv
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
from docx import Document
import pandas as pd


class MultiFormatParser:
    """Parse clinical documents in multiple formats."""

    def __init__(self, file_path: str):
        """Initialize parser with file path."""
        self.file_path = Path(file_path)
        self.extension = self.file_path.suffix.lower()

        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

    def parse(self) -> Tuple[List[Dict], str]:
        """
        Parse document and extract cases as table-like structures.
        Returns: (cases_list, source_format)
        """
        if self.extension == '.docx':
            return self._parse_docx(), 'docx'
        elif self.extension == '.pdf':
            return self._parse_pdf(), 'pdf'
        elif self.extension == '.xlsx':
            return self._parse_xlsx(), 'xlsx'
        elif self.extension == '.csv':
            return self._parse_csv(), 'csv'
        elif self.extension == '.txt':
            return self._parse_txt(), 'txt'
        else:
            raise ValueError(f"Unsupported file format: {self.extension}")

    def _parse_docx(self) -> List[Dict]:
        """Extract tables from Word document."""
        doc = Document(str(self.file_path))
        cases = []

        for table_idx, table in enumerate(doc.tables):
            case = self._table_to_dict(table, table_idx)
            if case:
                cases.append(case)

        print(f"✓ Extracted {len(cases)} cases from DOCX")
        return cases

    def _parse_pdf(self) -> List[Dict]:
        """Extract tables from PDF."""
        try:
            import pdfplumber
        except ImportError:
            print("⚠️  pdfplumber not installed. Install with: pip install pdfplumber")
            return []

        cases = []
        with pdfplumber.open(str(self.file_path)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    for table_idx, table in enumerate(tables):
                        case = self._table_array_to_dict(table, f"page_{page_idx}_table_{table_idx}")
                        if case:
                            cases.append(case)

        print(f"✓ Extracted {len(cases)} cases from PDF")
        return cases

    def _parse_xlsx(self) -> List[Dict]:
        """Extract data from Excel file."""
        excel_file = pd.ExcelFile(str(self.file_path))
        cases = []

        for sheet_idx, sheet_name in enumerate(excel_file.sheet_names):
            df = pd.read_excel(str(self.file_path), sheet_name=sheet_name)

            # Each row = one case
            for row_idx, row in df.iterrows():
                case = {}
                case['source_sheet'] = sheet_name
                case['source_row'] = row_idx

                # Convert row to text content
                content = []
                for col, value in row.items():
                    if pd.notna(value):
                        content.append(f"{col}: {value}")

                case['text_content'] = "\n".join(content)
                cases.append(case)

        print(f"✓ Extracted {len(cases)} rows from XLSX ({len(excel_file.sheet_names)} sheets)")
        return cases

    def _parse_csv(self) -> List[Dict]:
        """Extract data from CSV file."""
        cases = []

        with open(str(self.file_path), 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader):
                case = {}
                case['source_row'] = row_idx

                # Convert row to text content
                content = []
                for col, value in row.items():
                    if value and value.strip():
                        content.append(f"{col}: {value}")

                case['text_content'] = "\n".join(content)
                cases.append(case)

        print(f"✓ Extracted {len(cases)} rows from CSV")
        return cases

    def _parse_txt(self) -> List[Dict]:
        """Extract text from plain text file."""
        with open(str(self.file_path), 'r', encoding='utf-8') as f:
            content = f.read()

        # Split by common delimiters (---, ===, etc.)
        cases = []
        sections = content.split('\n---\n')
        if len(sections) == 1:
            sections = content.split('\n===\n')

        for idx, section in enumerate(sections):
            if section.strip():
                case = {
                    'case_index': idx,
                    'text_content': section.strip()
                }
                cases.append(case)

        # If no sections found, treat whole file as one case
        if not cases:
            cases.append({
                'case_index': 0,
                'text_content': content.strip()
            })

        print(f"✓ Extracted {len(cases)} sections from TXT")
        return cases

    def _table_to_dict(self, table, table_idx: int) -> Dict:
        """Convert Word table to dictionary."""
        case = {
            'table_index': table_idx,
            'cells': []
        }

        for row_idx, row in enumerate(table.rows):
            for cell_idx, cell in enumerate(row.cells):
                text = cell.text.strip()
                if text:
                    case['cells'].append({
                        'row': row_idx,
                        'col': cell_idx,
                        'text': text
                    })

        return case if case['cells'] else None

    def _table_array_to_dict(self, table: List[List], table_id: str) -> Dict:
        """Convert 2D array (from PDF) to dictionary."""
        case = {
            'table_id': table_id,
            'cells': []
        }

        for row_idx, row in enumerate(table):
            for col_idx, cell in enumerate(row):
                if cell and str(cell).strip():
                    case['cells'].append({
                        'row': row_idx,
                        'col': col_idx,
                        'text': str(cell).strip()
                    })

        return case if case['cells'] else None


def parse_clinical_document(file_path: str) -> Tuple[List[Dict], str]:
    """
    Main entry point for parsing clinical documents.

    Args:
        file_path: Path to document (.docx, .pdf, .xlsx, .csv, .txt)

    Returns:
        (cases_list, source_format)
    """
    parser = MultiFormatParser(file_path)
    return parser.parse()


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python multi_format_parser.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    cases, source_format = parse_clinical_document(file_path)

    print(f"\n📄 Source format: {source_format.upper()}")
    print(f"📊 Cases extracted: {len(cases)}")
    print(f"\n💾 Sample case structure:")
    if cases:
        print(json.dumps(cases[0], indent=2, default=str))
