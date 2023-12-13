# Import necessary libraries
import os
import openai
import streamlit as st
from io import BytesIO
import time
import base64
import re
from openai.types.beta.threads import MessageContentImageFile

api_key = os.environ.get("OPENAI_API_KEY")
auth_password = os.environ.get("AUTH_PASSWORD")
assistant_id_35 = os.environ.get("ASSISTANT_ID_35")
assistant_id_4 = os.environ.get("ASSISTANT_ID_4")

# Initialize the OpenAI client (ensure to set your API key in the sidebar within the app)
client = openai

# Initialize session state variables for file IDs and chat control
if "file_id_list" not in st.session_state:
    st.session_state.file_id_list = []

if "start_chat" not in st.session_state:
    st.session_state.start_chat = False

if "thread_id" not in st.session_state:
    st.session_state.thread_id = None

if "message_ids" not in st.session_state:
    st.session_state.message_ids = set()

if "in_progress" not in st.session_state:
    st.session_state.in_progress = False

if "assistant_id" not in st.session_state:
    st.session_state.assistant_id = assistant_id_4

# Set up the Streamlit page with a title and icon
st.set_page_config(page_title="Data Analysis Assistant", page_icon=":speech_balloon:")

# Define functions for uploading to OpenAI
def upload_to_openai(uploaded_file):
    """Upload a file to OpenAI and return its file ID."""
    response = client.files.create(file=uploaded_file, purpose="assistants")
    return response.id

# Create a sidebar for API key configuration and additional features
openai.api_key = None
st.sidebar.header("Authentication")
password = st.sidebar.text_input("Enter your password", type="password")
if password and password == auth_password:
    openai.api_key = api_key
elif len(password) > 0:
    st.sidebar.warning("Wrong password.")

# Select model
model = st.sidebar.selectbox(
    "Select a model",
    ("GPT-4 Turbo", "GPT-3.5 Turbo")
)
if model == "GPT-4 Turbo":
    st.session_state.assistant_id = assistant_id_4
else:
    st.session_state.assistant_id = assistant_id_35

# Additional features in the sidebar for web scraping and file uploading
st.sidebar.header("Files")

# Sidebar option for users to upload their own files
uploaded_file = st.sidebar.file_uploader("Upload a file to OpenAI", key="file_uploader")

# Button to upload a user's file and store the file ID
if st.sidebar.button("Upload File"):
    # Upload file provided by user
    if uploaded_file:
        try:
            additional_file_id = upload_to_openai(uploaded_file)
            st.session_state.file_id_list.append(additional_file_id)
            st.sidebar.write(f"File ID: {additional_file_id}")
        except openai.BadRequestError as e:
            st.sidebar.write(str(e))

# Display all file IDs
if st.session_state.file_id_list:
    st.sidebar.write("Uploaded File IDs:")
    for file_id in st.session_state.file_id_list:
        st.sidebar.write(file_id)
        # # Associate files with the assistant
        # assistant_file = client.beta.assistants.files.create(
        #     assistant_id=st.session_state.assistant_id, 
        #     file_id=file_id
        # )

st.sidebar.write('--------')

# Button to start the chat session
if st.sidebar.button("Start Chat"):
    st.session_state.start_chat = True
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id
    st.write("thread id: ", thread.id)

st.sidebar.write('Refresh the browser to clear data and rerun')

if st.sidebar.button("Delete All Uploaded Files"):
    for file in client.files.list().data:
        client.files.delete(file.id)

def create_file_link(filename, file_id):
    content = client.files.content(file_id)
    content_type = content.response.headers["content-type"]
    b64 = base64.b64encode(content.text.encode(content.encoding)).decode()
    link_tag = f'<a href="data:{content_type};base64,{b64}" download="{filename}">Download Link</a>'
    return link_tag

# Define the function to process messages with citations
def process_message_with_citations(message):
    """Extract content and annotations from the message and format citations as footnotes."""
    texts = []
    images = []
    for content in message.content:
        if not isinstance(content, MessageContentImageFile):
            message_content = content.text
            annotations = message_content.annotations if hasattr(message_content, 'annotations') else []
            citations = []
            # Iterate over the annotations and add footnotes
            for index, annotation in enumerate(annotations):
                # Replace the text with a footnote
                message_content.value = message_content.value.replace(annotation.text, f' [{index + 1}]')

                # Gather citations based on annotation attributes
                if (file_citation := getattr(annotation, 'file_citation', None)):
                    cited_file = client.files.retrieve(file_citation.file_id)
                    citations.append(f'[{index + 1}] {file_citation.quote} from {cited_file.filename}')
                elif (file_path := getattr(annotation, 'file_path', None)):
                    link_tag = create_file_link(annotation.text.split("/")[-1], file_path.file_id)
                    message_content.value = re.sub(r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", link_tag, message_content.value)
            if len(message_content.value) > 0:
                texts.append(message_content.value + '\n\n' + '\n'.join(citations))
        else:
            image_file = client.files.retrieve(content.image_file.file_id)
            image_content = client.files.content(content.image_file.file_id)
            image = BytesIO(image_content.read())
            images.append((image, image_file.filename))
    return '\n'.join(texts), images



# Main chat interface setup
st.title("Data Analysis Assistant")

# Only show the chat interface if the chat has been started
if st.session_state.start_chat:
    # Initialize the model and messages list if not already in session state
    if "openai_model" not in st.session_state:
        st.session_state.openai_model = "gpt-4-1106-preview"
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display existing messages in the chat
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for img, name in message.get("images", []):
                st.image(img, caption=name)

    # Chat input for the user
    if prompt := st.chat_input("What's up?", disabled=st.session_state.in_progress):
        # Add user message to the state and display it
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Add the user's message to the existing thread
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=prompt,
            file_ids=st.session_state.file_id_list
        )

        # Create a run with additional instructions
        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=st.session_state.assistant_id,
            instructions="Please answer the queries using the data provided in the files. When adding other information mark it clearly as such, with different color"
        )

        # Poll for the run to complete and retrieve the assistant's messages
        completed = False
        while not completed:
            st.session_state.in_progress = True
            run = client.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
            print("run.status:", run.status)
            messages = client.beta.threads.messages.list(thread_id=st.session_state.thread_id)
            assistant_messages_for_run = [
                message for message in messages 
                if message.role == "assistant"
            ]
            for message in reversed(assistant_messages_for_run):
                if message.id in st.session_state.message_ids:
                    continue
                full_text, images = process_message_with_citations(message)
                if len(full_text) == 0:
                    continue
                st.session_state.message_ids.add(message.id)
                st.session_state.messages.append({"role": "assistant", "content": full_text, "images": images})
                with st.chat_message("assistant"):
                    st.markdown(full_text, unsafe_allow_html=True)
                    for img, name in images:
                        st.image(img, caption=name)
            if run.status == "completed":
                completed = True
                st.session_state.in_progress = False
                print('messages', messages)
            else:
                time.sleep(10)
else:
    # Prompt to start the chat
    st.write("Please upload files and click 'Start Chat' to begin the conversation.")
