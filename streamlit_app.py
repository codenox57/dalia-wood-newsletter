import streamlit as st
import PyPDF2
import io
import base64
from PIL import Image
import os
from datetime import datetime
from anthropic import Anthropic

# Initialize the Anthropic client
anthropic = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

def extract_text_from_pdf(pdf_file):
    """
    Extract text content from uploaded PDF while preserving headers and footers.
    """
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text_content = ""
    
    for page in pdf_reader.pages:
        text_content += page.extract_text() + "\n"
    
    return text_content

def process_image(image_file):
    """
    Process uploaded image file and convert to base64 for API submission.
    """
    image = Image.open(image_file)
    buffered = io.BytesIO()
    image.save(buffered, format=image.format)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extract_text_from_response(response):
    """
    Extract plain text content from Claude's response, handling different response formats.
    """
    if hasattr(response, 'content'):
        if isinstance(response.content, list):
            # Handle case where content is a list of content blocks
            for block in response.content:
                if hasattr(block, 'text'):
                    return block.text
                elif isinstance(block, dict) and 'text' in block:
                    return block['text']
        elif hasattr(response.content, 'text'):
            return response.content.text
        else:
            return str(response.content)
    return str(response)

def generate_new_content(original_text, events_description, images):
    """
    Generate new newsletter content using Claude API, incorporating image descriptions
    and ensuring content references the provided images.
    """
    current_month = datetime.now().strftime("%B %Y")
    
    # Create image descriptions for the prompt
    image_descriptions = []
    for idx, image in enumerate(images, 1):
        image_b64 = process_image(image)
        image_descriptions.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/" + image.type.split('/')[-1],
                "data": image_b64
            }
        })
    
    text_content = f"""You are tasked with writing a new edition of the Dahlia Wood newsletter for {current_month}. 

I have provided you with {len(images)} images that will be included in the newsletter, along with new events to feature.

Please examine this previous newsletter to understand the tone, style, and formatting conventions:
{original_text}

Here are the events and updates to include in the new newsletter:
{events_description}

Important instructions:
1. Create entirely new content - this is a new edition, not an update of the old one
2. Only include events and information from the description provided above
3. Do not reference or include any events from the previous newsletter
4. You must incorporate natural references to the provided images in your content, as these will be included in the final newsletter
5. Maintain the same professional tone, style, and structural elements (like headers and section titles) as the original
6. Ensure all Dahlia Wood branding elements and formatting remain consistent
7. The newsletter should be dated {current_month}
8. When referencing images, use natural language that will make sense when the images are placed in the final layout (e.g., "As shown in the photograph above...")

Please write the complete new newsletter content following these instructions. Provide only the newsletter text content without any meta information or formatting marks."""

    # Combine text content with image descriptions for the API call
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Please analyze these images that will be included in the newsletter:"
                },
                *image_descriptions,
                {
                    "type": "text",
                    "text": text_content
                }
            ]
        }
    ]

    response = anthropic.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=2048,
        temperature=0.7,
        system="You are a business communication expert who specializes in writing newsletters while maintaining consistent organizational voice and branding. You should analyze the provided images and incorporate natural references to them in your newsletter content.",
        messages=messages
    )
    
    return extract_text_from_response(response)

def main():
    st.set_page_config(page_title="Dahlia Wood Newsletter Generator")
    st.title("Dahlia Wood Newsletter Generator")
    
    # Initialize session state for content and clipboard
    if 'generated_content' not in st.session_state:
        st.session_state.generated_content = None
    
    # Add current month display
    current_month = datetime.now().strftime("%B %Y")
    st.write(f"Generating newsletter for: {current_month}")
    
    # File uploads
    uploaded_pdf = st.file_uploader(
        "Upload Previous Newsletter PDF", 
        type=['pdf'], 
        help="Upload a previous newsletter to maintain consistent style and formatting"
    )
    
    uploaded_images = st.file_uploader(
        "Upload Images for Newsletter", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True,
        help="Upload images to be included in the new newsletter. The content will be written to reference these images naturally."
    )
    
    # Display uploaded images
    if uploaded_images:
        st.subheader("Uploaded Images")
        cols = st.columns(min(3, len(uploaded_images)))
        for idx, (image, col) in enumerate(zip(uploaded_images, cols)):
            col.image(image, caption=f"Image {idx + 1}", use_column_width=True)
    
    # Text input for new events
    events_description = st.text_area(
        "Describe Events to Include in the New Newsletter",
        help="Provide all events and updates that should be included in this month's newsletter. Only these events will be referenced in the new content."
    )
    
    if uploaded_pdf is not None and uploaded_images:
        # Generate content button
        if st.button("Generate New Content"):
            with st.spinner("Analyzing images and generating newsletter content..."):
                try:
                    original_text = extract_text_from_pdf(uploaded_pdf)
                    generated_content = generate_new_content(
                        original_text, 
                        events_description, 
                        uploaded_images
                    )
                    st.session_state.generated_content = generated_content
                except Exception as e:
                    st.error(f"Error generating content: {str(e)}")
        
        # Display content preview if available
        if st.session_state.generated_content:
            st.subheader("Generated Newsletter Content")
            
            # Create columns for the text area and copy button
            col1, col2 = st.columns([4, 1])
            
            with col1:
                edited_content = st.text_area(
                    "Review and Edit Content",
                    value=st.session_state.generated_content,
                    height=400
                )
            
            with col2:
                # Implement clipboard functionality using JavaScript
                st.markdown("""
                    <script>
                    function copyToClipboard() {
                        const textArea = document.querySelector('textarea[aria-label="Review and Edit Content"]');
                        textArea.select();
                        document.execCommand('copy');
                    }
                    </script>
                    """, unsafe_allow_html=True)
                
                if st.button("Copy to Clipboard", key="copy_button"):
                    st.write(
                        """
                        <script>copyToClipboard();</script>
                        Content copied!
                        """,
                        unsafe_allow_html=True
                    )

if __name__ == "__main__":
    main()