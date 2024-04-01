from flask import Flask, render_template, request, redirect, url_for, session
import boto3
import hashlib
import hmac
import base64
from botocore.exceptions import NoCredentialsError
from cognito_config import COGNITO_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET
import logging
import json


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'kqJEqJWSZCzkBgYX+1G0pCxoeymWLYY8c+1VUkVNT6w=' 


# Initialize Bedrock client
bedrock = boto3.client('bedrock-runtime')


app.config['COGNITO_REGION'] = COGNITO_REGION
app.config['COGNITO_USER_POOL_ID'] = COGNITO_USER_POOL_ID
app.config['COGNITO_CLIENT_ID'] = COGNITO_CLIENT_ID
app.config['COGNITO_CLIENT_SECRET'] = COGNITO_CLIENT_SECRET

def authenticate_user(username, password):
    client = boto3.client('cognito-idp', region_name=COGNITO_REGION)
    
    client_id = COGNITO_CLIENT_ID # Replace with your actual client ID
    client_secret = COGNITO_CLIENT_SECRET # Replace with your actual client secret
    
    # Calculate the SECRET_HASH
    message = username + client_id
    dig = hmac.new(str(client_secret).encode('utf-8'), 
                   msg=str(message).encode('utf-8'), 
                   digestmod=hashlib.sha256).digest()
    secret_hash = base64.b64encode(dig).decode()
    
    try:
        response = client.initiate_auth(
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password,
                'SECRET_HASH': secret_hash  # Include SECRET_HASH
            },
            ClientId=client_id,
        )
        
        # Ensure 'AuthenticationResult' is present in the response
        if 'AuthenticationResult' in response:
            logging.info(f"Authentication successful for user: {username}")
            return response['AuthenticationResult']['IdToken']
        else:
            logging.error(f"Authentication failed. Unexpected response: {response}")
            print(f"Authentication failed. Unexpected response: {response}")
            return None
    
    except NoCredentialsError as e:
        logging.error(f"Error: {e}")
        print(f"Error: {e}")
        return None
    except Exception as e:
        logging.error(f"Authentication failed: {e}")
        print(f"Authentication failed: {e}")
        return None
	

@app.route('/')
def home():
    if 'id_token' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        id_token = authenticate_user(username, password)
        if id_token:
            session['id_token'] = id_token
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Function to call Bedrock model
def call_bedrock_model(topic):
    instruction = f"""
    You are a world-class writer. Please write a sweet bedtime story about {topic}.
    """

    body = {
        "inputText": instruction,
        "textGenerationConfig": {
            "maxTokenCount": 1024,
            "temperature": 0.2,
            "topP": 0.9,
            "stopSequences": ["User:"]
        }
    }

    try:
        response = bedrock.invoke_model_with_response_stream(
            modelId='amazon.titan-text-express-v1',
            body=json.dumps(body)
        )

        story = ""
        for event in response.get('body', []):
            chunk = event.get('chunk')
            if chunk:
                message = json.loads(chunk.get("bytes").decode())
                story += message.get('outputText', '')
        return story

    except NoCredentialsError as e:
        print(f"Error: {e}")
        logging.error(f"Error: {e}")
        return None
    except Exception as e:
        print(f"Error calling Bedrock model: {e}")
        logging.error(f"Error calling Bedrock model: {e}")
        return None
    
@app.route('/generate-story', methods=["POST"])
def generate_story():
    if 'id_token' not in session:
        return redirect(url_for('login'))

    topic = request.form.get("topic")
    if not topic:
        return render_template('index.html', error="Please provide a topic for the story.")

    story = call_bedrock_model(topic)
    if story is None:
        return render_template('index.html', error="Failed to generate story.")
    
    return render_template('index.html', story=story)