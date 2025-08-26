import re
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup

def parse_email(raw_email: bytes):
    # Parse raw email using default policy
    msg = BytesParser(policy=policy.default).parsebytes(raw_email)

    # Extract headers
    email_from = msg['From']
    email_to = msg['To']

    # Extract body (handle multipart)
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                body = part.get_content()
                break
    else:
        if msg.get_content_type() == 'text/html':
            body = msg.get_content()

    # Parse HTML to extract OTP
    soup = BeautifulSoup(body, 'html.parser')
    text = soup.get_text()
    match = re.search(r'\b(\d{4})\b', text)
    otp = match.group(1) if match else None

    return {
        'from': email_from,
        'to': email_to,
        'otp': otp,
    }

# Example usage
with open("sample_email.eml", "rb") as f:
    raw_email_bytes = f.read()

result = parse_email(raw_email_bytes)
print(result)
