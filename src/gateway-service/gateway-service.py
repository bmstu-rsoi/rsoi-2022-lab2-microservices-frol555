import os
from flask import Flask, request, Response
import requests

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

baseUrlBonus = 'http://10.5.0.4:8050'
baseUrlFlight = 'http://10.5.0.5:8060'
baseUrlTickets = 'http://10.5.0.6:8070'


@app.route('/')
def GWS_hello_world():
    statement = 'Gateway service!'
    return statement


@app.route('/api/v1/flights', methods=['GET'])
def GWS_get_flights():
    headers = {'Content-type': 'application/json'}
    param = dict(request.args)
    response = requests.get(baseUrlFlight + '/api/v1/flights', params=param, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        return Response(status=404)


@app.route('/api/v1/privilege', methods=['GET'])
def GWS_get_privilege():
    response = requests.get(baseUrlBonus + '/api/v1/privilege', headers=request.headers)

    if response.status_code == 200:
        return response.json()
    else:
        return Response(status=404)


@app.route('/api/v1/me', methods=['GET'])
def GWS_get_me_info():
    result = dict()
    result['tickets'] = GWS_get_tickets()
    result['privilege'] = GWS_get_privilege()
    del result['privilege']['history']
    return result


@app.route('/api/v1/tickets', methods=['GET'])
def GWS_get_tickets():

    # Get ticket Uid, flight number and status
    info_tickets = requests.get(baseUrlTickets + '/api/v1/tickets', headers=request.headers).json()

    for ticket in info_tickets:
        info_flights = requests.get(baseUrlFlight + '/api/v1/flights/exist', data=ticket['flightNumber']).json()
        ticket['fromAirport'] = info_flights['fromAirport']
        ticket['toAirport'] = info_flights['toAirport']
        ticket['date'] = info_flights['date']
        ticket['price'] = info_flights['price']

    return info_tickets


@app.route('/api/v1/tickets', methods=['POST'])
def GWS_post_tickets():

    # Get purchase information
    buy_info = request.json

    # Get username
    username = request.headers['X-User-Name']

    # Checking the existing flight number
    flight_exist = requests.get(baseUrlFlight + '/api/v1/flights/exist', data=buy_info['flightNumber']).json()

    # Return Error: 404 Not Found if flight number don't exist
    if not flight_exist:
        return Response(status=404)

    # Information for the ticket database
    data = {'username': username,
            'flightNumber': flight_exist['flightNumber'],
            'price': flight_exist['price'],
            'status': 'PAID'}

    # Get ticket UID
    ticket_uid = requests.post(baseUrlTickets + '/api/v1/tickets/buy', json=data)

    # Fill the first part of the response
    response = dict()
    response['ticketUid'] = ticket_uid.text
    response['flightNumber'] = flight_exist['flightNumber']
    response['fromAirport'] = flight_exist['fromAirport']
    response['toAirport'] = flight_exist['toAirport']
    response['date'] = flight_exist['date']
    response['price'] = flight_exist['price']
    response['status'] = 'PAID'

    # Processing bonus points (the second part of the response)
    if buy_info['paidFromBalance']:
        # Debiting from the bonus account
        data = {'username': username, 'ticketUid': ticket_uid.text, 'price': int(flight_exist['price'])}
        paid_by_bonuses = int(requests.post(baseUrlBonus + '/api/v1/privilege/debit', json=data).text)

        response['paidByMoney'] = data['price'] - paid_by_bonuses
        response['paidByBonuses'] = paid_by_bonuses
    else:
        # Replenishment of the bonus account
        data = {'username': username, 'ticketUid': ticket_uid.text, 'price': int(flight_exist['price'])}
        requests.post(baseUrlBonus + '/api/v1/privilege/replenishment', json=data)

        response['paidByMoney'] = flight_exist['price']
        response['paidByBonuses'] = 0

    # Information about privileges after ticket purchase (the third part of the response)
    privilege_info = requests.get(baseUrlBonus + '/api/v1/privilege', headers=request.headers).json()
    del privilege_info['history']

    response['privilege'] = privilege_info

    return response


@app.route('/api/v1/tickets/<string:ticketUid>', methods=['GET'])
def GWS_get_ticket_by_uid(ticketUid):

    # Get flight number and status
    info_tickets = requests.get(baseUrlTickets + f'/api/v1/tickets/{ticketUid}', headers=request.headers)

    if info_tickets.status_code != 200:
        return Response(status=404)

    info_tickets = info_tickets.json()

    # Get flight number and status
    info_flights = requests.get(baseUrlFlight + '/api/v1/flights/exist', data=info_tickets['flightNumber']).json()

    response = dict()
    response['ticketUid'] = ticketUid
    response['flightNumber'] = info_tickets['flightNumber']
    response['fromAirport'] = info_flights['fromAirport']
    response['toAirport'] = info_flights['toAirport']
    response['date'] = info_flights['date']
    response['price'] = info_flights['price']
    response['status'] = info_tickets['status']

    return response


@app.route('/api/v1/tickets/<string:ticketUid>', methods=['DELETE'])
def GWS_ticket_refund(ticketUid):
    tickets_response = requests.delete(baseUrlTickets + f'/api/v1/tickets/{ticketUid}')
    if tickets_response.status_code != 204:
        return Response(status=404)

    privilege_response = requests.delete(baseUrlBonus + f'/api/v1/privilege/{ticketUid}', headers=request.headers)
    if privilege_response.status_code != 204:
        return Response(status=404)

    return Response(status=204)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, port=8080, host="0.0.0.0")
