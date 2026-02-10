"""
File and Media Processing for Telegram Agent
Handles images, PDFs, documents, and other media files
"""

import os
import io
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class ProcessedFile:
    """Result of processing a file."""
    filename: str
    mime_type: str
    size: int
    content_type: str  # 'text', 'image', 'pdf', 'document', 'unknown'
    text_content: Optional[str] = None
    base64_image: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class FileProcessor:
    """
    Processes various file types sent via Telegram.
    
    Supports:
    - Images (OCR, description, base64 encoding)
    - PDFs (text extraction, metadata)
    - Text files (direct reading)
    - Office documents (docx, xlsx, etc.)
    - Archives (zip listing)
    """
    
    SUPPORTED_IMAGES = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
    SUPPORTED_DOCUMENTS = {'.pdf', '.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt'}
    SUPPORTED_TEXT = {'.txt', '.md', '.json', '.yaml', '.yml', '.csv', '.py', '.js', '.html', '.css'}
    SUPPORTED_ARCHIVES = {'.zip', '.tar', '.gz', '.tgz', '.bz2'}
    
    def __init__(self, max_file_size_mb: int = 20):
        """
        Initialize file processor.
        
        Args:
            max_file_size_mb: Maximum file size to process in MB
        """
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check which optional dependencies are available."""
        self.has_pil = False
        self.has_pytesseract = False
        self.has_pymupdf = False
        self.has_docx = False
        
        try:
            from PIL import Image
            self.has_pil = True
        except ImportError:
            logger.warning("PIL not available - image processing disabled")
        
        try:
            import pytesseract
            self.has_pytesseract = True
        except ImportError:
            logger.warning("pytesseract not available - OCR disabled")
        
        try:
            import fitz  # PyMuPDF
            self.has_pymupdf = True
        except ImportError:
            logger.warning("PyMuPDF not available - PDF processing limited")
        
        try:
            import docx
            self.has_docx = True
        except ImportError:
            logger.warning("python-docx not available - DOCX processing disabled")
    
    async def process_telegram_file(self, file_obj, bot) -> ProcessedFile:
        """
        Process a file from Telegram.
        
        Args:
            file_obj: Telegram File object
            bot: Telegram bot instance
            
        Returns:
            ProcessedFile with extracted content
        """
        try:
            # Get file info
            file_id = file_obj.file_id
            file_info = await bot.get_file(file_id)
            
            # Check file size
            if file_info.file_size and file_info.file_size > self.max_file_size:
                return ProcessedFile(
                    filename=file_obj.file_name or "unknown",
                    mime_type=file_obj.mime_type or "application/octet-stream",
                    size=file_info.file_size or 0,
                    content_type='unknown',
                    error=f"File too large: {file_info.file_size} bytes (max: {self.max_file_size})"
                )
            
            # Download file
            file_bytes = await file_info.download_as_bytearray()
            
            # Determine file type from filename or mime type
            filename = getattr(file_obj, "file_name", None) or f"file_{file_id}"
            ext = Path(filename).suffix.lower()
            mime_type = getattr(file_obj, "mime_type", None) or "application/octet-stream"
            
            # Route to appropriate processor
            if ext in self.SUPPORTED_IMAGES or mime_type.startswith('image/'):
                return await self._process_image(file_bytes, filename, mime_type)
            elif ext == '.pdf' or mime_type == 'application/pdf':
                return await self._process_pdf(file_bytes, filename)
            elif ext in {'.docx'} or mime_type in {
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/msword'
            }:
                return await self._process_docx(file_bytes, filename)
            elif ext in {'.xlsx'} or mime_type in {
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-excel'
            }:
                return await self._process_xlsx(file_bytes, filename)
            elif ext in self.SUPPORTED_TEXT or mime_type.startswith('text/'):
                return await self._process_text(file_bytes, filename, mime_type)
            elif ext in self.SUPPORTED_ARCHIVES:
                return await self._process_archive(file_bytes, filename, ext)
            else:
                return ProcessedFile(
                    filename=filename,
                    mime_type=mime_type,
                    size=len(file_bytes),
                    content_type='unknown',
                    error=f"Unsupported file type: {ext}"
                )
                
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            return ProcessedFile(
                filename=getattr(file_obj, 'file_name', 'unknown'),
                mime_type=getattr(file_obj, 'mime_type', 'application/octet-stream'),
                size=0,
                content_type='unknown',
                error=f"Processing error: {str(e)}"
            )
    
    async def _process_image(self, file_bytes: bytearray, filename: str, 
                            mime_type: str) -> ProcessedFile:
        """Process an image file - encode to base64 and optionally OCR."""
        try:
            # Encode to base64
            base64_data = base64.b64encode(file_bytes).decode('utf-8')
            
            result = ProcessedFile(
                filename=filename,
                mime_type=mime_type,
                size=len(file_bytes),
                content_type='image',
                base64_image=base64_data,
                metadata={'width': 0, 'height': 0}
            )
            
            # Get image dimensions if PIL available
            if self.has_pil:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(file_bytes))
                result.metadata['width'] = img.width
                result.metadata['height'] = img.height
                result.metadata['mode'] = img.mode
            
            # OCR if pytesseract available
            if self.has_pytesseract:
                import pytesseract
                from PIL import Image
                import io
                
                try:
                    img = Image.open(io.BytesIO(file_bytes))
                    text = pytesseract.image_to_string(img)
                    if text.strip():
                        result.text_content = text.strip()
                        result.metadata['ocr'] = True
                except Exception as e:
                    logger.warning(f"OCR failed: {e}")
                    result.metadata['ocr'] = False
            
            return result
            
        except Exception as e:
            return ProcessedFile(
                filename=filename,
                mime_type=mime_type,
                size=len(file_bytes),
                content_type='image',
                error=f"Image processing error: {str(e)}"
            )
    
    async def _process_pdf(self, file_bytes: bytearray, filename: str) -> ProcessedFile:
        """Process a PDF file - extract text and metadata."""
        try:
            if self.has_pymupdf:
                import fitz
                import io
                
                doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
                
                # Extract text from all pages
                text_parts = []
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    text_parts.append(f"--- Page {page_num + 1} ---\n{page.get_text()}")
                
                # Get metadata
                metadata = {
                    'pages': len(doc),
                    'title': doc.metadata.get('title', ''),
                    'author': doc.metadata.get('author', ''),
                    'subject': doc.metadata.get('subject', ''),
                }
                
                doc.close()
                
                return ProcessedFile(
                    filename=filename,
                    mime_type='application/pdf',
                    size=len(file_bytes),
                    content_type='pdf',
                    text_content="\n\n".join(text_parts),
                    metadata=metadata
                )
            else:
                return ProcessedFile(
                    filename=filename,
                    mime_type='application/pdf',
                    size=len(file_bytes),
                    content_type='pdf',
                    error="PyMuPDF not installed - PDF text extraction unavailable"
                )
                
        except Exception as e:
            return ProcessedFile(
                filename=filename,
                mime_type='application/pdf',
                size=len(file_bytes),
                content_type='pdf',
                error=f"PDF processing error: {str(e)}"
            )
    
    async def _process_docx(self, file_bytes: bytearray, filename: str) -> ProcessedFile:
        """Process a DOCX file - extract text."""
        try:
            if self.has_docx:
                from docx import Document
                import io
                
                doc = Document(io.BytesIO(file_bytes))
                
                # Extract text from paragraphs
                text_parts = []
                for para in doc.paragraphs:
                    if para.text.strip():
                        text_parts.append(para.text)
                
                # Also extract from tables
                for table in doc.tables:
                    for row in table.rows:
                        row_text = []
                        for cell in row.cells:
                            row_text.append(cell.text.strip())
                        if any(row_text):
                            text_parts.append(" | ".join(row_text))
                
                return ProcessedFile(
                    filename=filename,
                    mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    size=len(file_bytes),
                    content_type='document',
                    text_content="\n\n".join(text_parts),
                    metadata={'paragraphs': len(doc.paragraphs), 'tables': len(doc.tables)}
                )
            else:
                return ProcessedFile(
                    filename=filename,
                    mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    size=len(file_bytes),
                    content_type='document',
                    error="python-docx not installed - DOCX processing unavailable"
                )
                
        except Exception as e:
            return ProcessedFile(
                filename=filename,
                mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                size=len(file_bytes),
                content_type='document',
                error=f"DOCX processing error: {str(e)}"
            )
    
    async def _process_xlsx(self, file_bytes: bytearray, filename: str) -> ProcessedFile:
        """Process an XLSX file - extract data as text."""
        try:
            # Try to use openpyxl if available
            try:
                import openpyxl
                import io
                
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                
                sheet_texts = []
                for sheet_name in wb.sheetnames:
                    sheet = wb[sheet_name]
                    sheet_texts.append(f"=== Sheet: {sheet_name} ===")
                    
                    # Get all rows
                    for row in sheet.iter_rows(values_only=True):
                        row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
                        if row_text.strip():
                            sheet_texts.append(row_text)
                
                return ProcessedFile(
                    filename=filename,
                    mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    size=len(file_bytes),
                    content_type='document',
                    text_content="\n".join(sheet_texts),
                    metadata={'sheets': len(wb.sheetnames)}
                )
            except ImportError:
                return ProcessedFile(
                    filename=filename,
                    mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    size=len(file_bytes),
                    content_type='document',
                    error="openpyxl not installed - XLSX processing unavailable"
                )
                
        except Exception as e:
            return ProcessedFile(
                filename=filename,
                mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                size=len(file_bytes),
                content_type='document',
                error=f"XLSX processing error: {str(e)}"
            )
    
    async def _process_text(self, file_bytes: bytearray, filename: str, 
                          mime_type: str) -> ProcessedFile:
        """Process a text file - decode and return content."""
        try:
            # Try different encodings
            text = None
            used_encoding = "utf-8"
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    text = file_bytes.decode(encoding)
                    used_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
            
            if text is None:
                text = file_bytes.decode('utf-8', errors='replace')
                used_encoding = "utf-8-lossy"
            
            return ProcessedFile(
                filename=filename,
                mime_type=mime_type,
                size=len(file_bytes),
                content_type='text',
                text_content=text,
                metadata={'encoding': used_encoding}
            )
            
        except Exception as e:
            return ProcessedFile(
                filename=filename,
                mime_type=mime_type,
                size=len(file_bytes),
                content_type='text',
                error=f"Text processing error: {str(e)}"
            )
    
    async def _process_archive(self, file_bytes: bytearray, filename: str, 
                              ext: str) -> ProcessedFile:
        """Process an archive file - list contents."""
        try:
            import io
            contents = []
            
            if ext == '.zip':
                import zipfile
                with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as zf:
                    contents = zf.namelist()
            elif ext in {'.tar', '.gz', '.tgz', '.bz2'}:
                import tarfile
                mode = 'r:gz' if ext in {'.gz', '.tgz'} else 'r:bz2' if ext == '.bz2' else 'r'
                with tarfile.open(fileobj=io.BytesIO(file_bytes), mode=mode) as tf:
                    contents = [m.name for m in tf.getmembers()]
            
            return ProcessedFile(
                filename=filename,
                mime_type='application/zip' if ext == '.zip' else 'application/x-tar',
                size=len(file_bytes),
                content_type='archive',
                text_content="Archive contents:\n" + "\n".join(contents[:100]),  # Limit listing
                metadata={'total_files': len(contents)}
            )
            
        except Exception as e:
            return ProcessedFile(
                filename=filename,
                mime_type='application/octet-stream',
                size=len(file_bytes),
                content_type='archive',
                error=f"Archive processing error: {str(e)}"
            )
    
    def format_for_llm(self, processed: ProcessedFile) -> Dict[str, Any]:
        """
        Format a processed file for consumption by the LLM.
        
        Returns a dict that can be added to the conversation context.
        """
        result = {
            "type": processed.content_type,
            "filename": processed.filename,
            "mime_type": processed.mime_type,
            "size": processed.size,
            "metadata": processed.metadata or {}
        }
        
        if processed.error:
            result["error"] = processed.error
            return result
        
        if processed.content_type == 'image':
            result["image_base64"] = processed.base64_image
            if processed.text_content:  # OCR text
                result["ocr_text"] = processed.text_content
        
        elif processed.content_type in {'pdf', 'document', 'text'}:
            # Truncate very long text
            text = processed.text_content or ""
            if len(text) > 50000:
                text = text[:50000] + "\n\n... [truncated, file too large]"
            result["content"] = text
        
        return result


# Global file processor instance
_global_processor: Optional[FileProcessor] = None


def get_file_processor(max_file_size_mb: int = 20) -> FileProcessor:
    """Get or create the global file processor."""
    global _global_processor
    if _global_processor is None:
        _global_processor = FileProcessor(max_file_size_mb)
    return _global_processor
