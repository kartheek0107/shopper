import firebase_admin
from firebase_admin import credentials, messaging

# Initialize once at startup
cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred)


# Send notification function
def send_notification(fcm_token, order_data):
    message = messaging.Message(
        data={
            'type': 'new_request',
            'title': 'New Delivery Available!',
            'body': f"Pick up from {order_data['pickup_area']} to {order_data['drop_area']}",
            'order_id': order_data['id'],
            'pickup_area': order_data['pickup_area'],
            'drop_area': order_data['drop_area'],
            'reward': str(order_data['reward']),
            'deadline': order_data['deadline'],
        },
        token=fcm_token,
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                title='New Delivery Available!',
                body=f"Pick up from {order_data['pickup_area']} to {order_data['drop_area']}",
                icon='ic_notification',
                color='#009688',
                sound='default',
            )
        )
    )

    response = messaging.send(message)
    print(f'Successfully sent message: {response}')