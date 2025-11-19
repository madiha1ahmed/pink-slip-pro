from twilio.rest import Client

account_sid = 'ACf71e43846bbe8466b3730273568fc5fd'
auth_token = '692cb59e658e3599e2015a1c31a1538d'
client = Client(account_sid, auth_token)

message = client.messages.create(
  from_='whatsapp:+14155238886',
  body="Twilio Test",
  to='whatsapp:+19053251764'
)

print(f"📤 WhatsApp sent to | SID: {message.sid}")

from twilio.rest import Client

account_sid = 'AC71e25bb8329e1c9e635cd13026c6c54c'
auth_token = 'e1742e8637f242a461e59c7bda2b3a89'
client = Client(account_sid, auth_token)

message = client.messages.create(
  from_='whatsapp:+14155238886',
  content_sid='HXb5b62575e6e4ff6129ad7c8efe1f983e',
  content_variables='{"1":"12/1","2":"3pm"}',
  to='whatsapp:+919108108138'
)

print(message.sid)



