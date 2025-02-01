import streamlit as st
import PyPDF2
import io
from PIL import Image
import cohere
import fitz  # PyMuPDF
import tempfile
import os
from datetime import datetime

# Initialize the Cohere client - users will need to set their API key
cohere_api_key = os.getenv('COHERE_API_KEY')
co = cohere.Client(cohere_api_key)

def extract_text_from_pdf(pdf_file):
    """
    Extract text content from uploaded PDF while preserving headers and footers.
    Returns the text content and PDF metadata for reconstruction.
    """
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text_content = ""
    
    for page in pdf_reader.pages:
        text_content += page.extract_text() + "\n"
    
    return text_content

def generate_new_content(original_text, events_description):
    """
    Generate new newsletter content using Cohere API while maintaining original style.
    Includes current month update in the prompt.
    """
    current_month = datetime.now().strftime("%B %Y")
    
    prompt = f"""
    You are tasked with rewriting the Dahlia Wood newsletter while maintaining its original style and structure.
    
    Original newsletter content:
    {original_text}
    
    Recent events to incorporate:
    {events_description}
    
    Important instructions:
    1. Update all references to the publication month/date to {current_month}
    2. Maintain the same tone, style, and structure as the original
    3. Preserve any headers, footers, and section titles
    4. Incorporate the new events naturally into the existing sections
    5. Ensure all branding elements and formatting remain consistent
    
    Please rewrite the newsletter content following these instructions.
    """
    
    response = co.generate(
        prompt=prompt,
        max_tokens=2048,
        temperature=0.7,
        k=0,
        stop_sequences=[],
        return_likelihoods='NONE'
    )
    
    return response.generations[0].text

def calculate_text_blocks(page_rect, image_rects):
    """
    Calculate the available text blocks around images.
    Returns a list of rectangles where text can be placed.
    """
    margin = 50  # Margin from page edges
    text_blocks = []
    
    # Initialize with full page area minus margins
    available_rect = fitz.Rect(
        margin,
        margin,
        page_rect.width - margin,
        page_rect.height - margin
    )
    
    for img_rect in image_rects:
        # Add text block above image
        if img_rect.y0 > available_rect.y0 + margin:
            text_blocks.append(fitz.Rect(
                available_rect.x0,
                available_rect.y0,
                available_rect.x1,
                img_rect.y0 - margin
            ))
        
        # Add text block beside image (left)
        if img_rect.x0 > available_rect.x0 + margin:
            text_blocks.append(fitz.Rect(
                available_rect.x0,
                img_rect.y0,
                img_rect.x0 - margin,
                img_rect.y1
            ))
        
        # Add text block beside image (right)
        if img_rect.x1 < available_rect.x1 - margin:
            text_blocks.append(fitz.Rect(
                img_rect.x1 + margin,
                img_rect.y0,
                available_rect.x1,
                img_rect.y1
            ))
        
        # Update available rectangle for text below the image
        available_rect.y0 = img_rect.y1 + margin
    
    # Add remaining space below last image
    if available_rect.y0 < available_rect.y1 - margin:
        text_blocks.append(available_rect)
    
    return text_blocks

def create_new_pdf(original_pdf, new_text, new_images):
    """
    Create a new PDF with updated content and images, implementing proper text wrapping.
    """
    # Open the original PDF
    doc = fitz.open(stream=original_pdf.read(), filetype="pdf")
    
    # Create a new PDF document
    new_doc = fitz.open()
    
    # Process each page
    for page_num in range(len(doc)):
        # Copy the original page
        page = doc[page_num]
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        
        # Clear existing content while preserving formatting
        new_page.clean_contents()
        
        # Calculate image positions and create image rectangles
        image_rects = []
        if new_images and page_num < len(new_images):
            img = Image.open(new_images[page_num])
            # Scale image while maintaining aspect ratio
            img_width = 300  # Desired width
            aspect_ratio = img.height / img.width
            img_height = int(img_width * aspect_ratio)
            
            # Position image in upper right
            img_rect = fitz.Rect(
                new_page.rect.width - img_width - 50,  # 50px margin from right
                50,  # 50px margin from top
                new_page.rect.width - 50,
                50 + img_height
            )
            image_rects.append(img_rect)
            
            # Insert image
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes = img_bytes.getvalue()
            new_page.insert_image(img_rect, stream=img_bytes)
        
        # Calculate text blocks around images
        text_blocks = calculate_text_blocks(new_page.rect, image_rects)
        
        # Split text into paragraphs
        paragraphs = new_text.split('\n\n')
        
        # Insert text into available blocks
        current_block = 0
        current_y = text_blocks[0].y0
        font_size = 11
        line_height = font_size * 1.2
        
        for paragraph in paragraphs:
            if current_block >= len(text_blocks):
                break
                
            text_block = text_blocks[current_block]
            
            # Calculate if paragraph fits in current block
            text_height = len(paragraph.split('\n')) * line_height
            if current_y + text_height > text_block.y1:
                current_block += 1
                if current_block >= len(text_blocks):
                    break
                text_block = text_blocks[current_block]
                current_y = text_block.y0
            
            # Insert paragraph
            new_page.insert_text(
                point=(text_block.x0, current_y),
                text=paragraph,
                fontsize=font_size,
                fontname="helv",
                color=(0, 0, 0)
            )
            current_y += text_height + font_size  # Add space between paragraphs
    
    # Save to bytes buffer
    output_buffer = io.BytesIO()
    new_doc.save(output_buffer)
    output_buffer.seek(0)
    
    return output_buffer

def main():
    st.set_page_config(page_title="Dahlia Wood Newsletter Generator")
    st.title("Dahlia Wood Newsletter Generator")
    
    # Add current month display
    current_month = datetime.now().strftime("%B %Y")
    st.write(f"Generating newsletter for: {current_month}")
    
    # File uploads
    uploaded_pdf = st.file_uploader("Upload Original Newsletter PDF", type=['pdf'])
    uploaded_images = st.file_uploader("Upload New Images", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    
    # Text input for new events
    events_description = st.text_area("Describe Recent Events to Include")
    
    if uploaded_pdf is not None:
        # Extract text from original PDF
        original_text = extract_text_from_pdf(uploaded_pdf)
        
        if st.button("Generate New Content"):
            with st.spinner("Generating new content..."):
                # Generate new content using Cohere
                new_content = generate_new_content(original_text, events_description)
                
                # Display new content for review
                st.subheader("Generated Content Preview")
                st.text_area("Review and Edit Content", new_content, height=300)
                
                # Button to create final PDF
                if st.button("Create Final PDF"):
                    with st.spinner("Creating PDF..."):
                        # Reset file pointer
                        uploaded_pdf.seek(0)
                        
                        # Create new PDF
                        pdf_buffer = create_new_pdf(uploaded_pdf, new_content, uploaded_images)
                        
                        # Offer download
                        st.download_button(
                            label="Download New Newsletter",
                            data=pdf_buffer,
                            file_name=f"dahlia_wood_newsletter_{current_month.lower().replace(' ', '_')}.pdf",
                            mime="application/pdf"
                        )

if __name__ == "__main__":
    main()