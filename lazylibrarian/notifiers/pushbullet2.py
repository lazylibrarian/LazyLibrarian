#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import lib.requests as requests
import lib.simplejson as json
from lib.requests.auth import HTTPBasicAuth

# from websocket import create_connection

HOST = "https://api.pushbullet.com/v2"


class PushBullet:

    def __init__(self, apiKey):
        self.apiKey = apiKey

    def _request(self, method, url, postdata=None, params=None, files=None):
        headers = {"Accept": "application/json",
                   "Content-Type": "application/json",
                   "User-Agent": "pyPushBullet"}

        if postdata:
            postdata = json.dumps(postdata)

        r = requests.request(method,
                             url,
                             data=postdata,
                             params=params,
                             headers=headers,
                             files=files,
                             auth=HTTPBasicAuth(self.apiKey, ""))

        r.raise_for_status()
        return r.json()

    def addDevice(self, device_name):
        """ Push a note
            https://docs.pushbullet.com/v2/pushes
            Arguments:
            device_name -- Human readable name for device
            type -- stream, thats all there is currently
        """

        data = {"nickname": device_name,
                "type": "stream"
                }
        return self._request("POST", HOST + "/devices", data)

    def getDevices(self):
        """ Get devices
            https://docs.pushbullet.com/v2/devices
            Get a list of devices, and data about them.
        """

        return self._request("GET", HOST + "/devices")["devices"]

    def deleteDevice(self, device_iden):
        """ Delete a device
            https://docs.pushbullet.com/v2/devices
            Arguments:
            device_iden -- iden of device to push to
        """

        return self._request("DELETE", HOST + "/devices/" + device_iden)

    def pushNote(self, recipient, title, body, recipient_type="device_iden"):
        """ Push a note
            https://docs.pushbullet.com/v2/pushes
            Arguments:
            recipient -- a recipient
            title -- a title for the note
            body -- the body of the note
            recipient_type -- a type of recipient (device, email, channel or client)
        """

        data = {"type": "note", "title": title, "body": body, recipient_type: recipient}

        return self._request("POST", HOST + "/pushes", data)

    def pushAddress(self, recipient, name, address, recipient_type="device_iden"):
        """ Push an address
            https://docs.pushbullet.com/v2/pushes
            Arguments:
            recipient -- a recipient
            name -- name for the address, eg "Bobs house"
            address -- address of the address
            recipient_type -- a type of recipient (device, email, channel or client)
        """

        data = {"type": "address", "name": name, "address": address, recipient_type: recipient}

        return self._request("POST", HOST + "/pushes", data)

    def pushList(self, recipient, title, items, recipient_type="device_iden"):
        """ Push a list
            https://docs.pushbullet.com/v2/pushes
            Arguments:
            recipient -- a recipient
            title -- a title for the list
            items -- a list of items
            recipient_type -- a type of recipient (device, email, channel or client)
        """

        data = {"type": "list", "title": title, "items": items, recipient_type: recipient}

        return self._request("POST", HOST + "/pushes", data)

    def pushLink(self, recipient, title, url, recipient_type="device_iden"):
        """ Push a link
            https://docs.pushbullet.com/v2/pushes
            Arguments:
            recipient -- a recipient
            title -- link title
            url -- link url
            recipient_type -- a type of recipient (device, email, channel or client)
        """

        data = {"type": "link", "title": title, "url": url, recipient_type: recipient}

        return self._request("POST", HOST + "/pushes", data)

    def pushFile(self, recipient, file_name, body, fobj, file_type=None, recipient_type="device_iden"):
        """ Push a file
            https://docs.pushbullet.com/v2/pushes
            https://docs.pushbullet.com/v2/upload-request
            Arguments:
            recipient -- a recipient
            file_name -- name of the file
            fobj -- a file object
            file_type -- file mimetype, if not set, python-magic will be used
            recipient_type -- a type of recipient (device, email, channel or client)
        """

        if not file_type:
            try:
                import magic
                file_type = magic.from_buffer(fobj.read(1024))
                fobj.seek(0)
            except:
                file_type = ""

        data = {"file_name": file_name,
                "file_type": file_type}

        upload_request = self._request("GET",
                                       HOST + "/upload-request",
                                       None,
                                       data)

        upload = requests.post(upload_request["upload_url"],
                               data=upload_request["data"],
                               files={"file": fobj},
                               headers={"User-Agent": "pyPushBullet"})

        upload.raise_for_status()

        data = {"type": "file", "file_name": file_name, "file_type": file_type, "file_url": upload_request["file_url"],
                "body": body, recipient_type: recipient}

        return self._request("POST", HOST + "/pushes", data)

    def getPushHistory(self, modified_after=0, cursor=None):
        """ Get Push History
            https://docs.pushbullet.com/v2/pushes
            Returns a list of pushes
            Arguments:
            modified_after -- Request pushes modified after this timestamp
            cursor -- Request another page of pushes (if necessary)
        """
        data = {"modified_after": modified_after}
        if cursor:
            data["cursor"] = cursor
        return self._request("GET", HOST + "/pushes", None, data)["pushes"]

    def deletePush(self, push_iden):
        """ Delete push
            https://docs.pushbullet.com/v2/pushes
            Arguments:
            push_iden -- the iden of the push to delete
        """
        return self._request("DELETE", HOST + "/pushes/" + push_iden)

    def getContacts(self):
        """ Gets your contacts
            https://docs.pushbullet.com/v2/contacts
            returns a list of contacts
        """
        return self._request("GET", HOST + "/contacts")["contacts"]

    def deleteContact(self, contact_iden):
        """ Delete a contact
            https://docs.pushbullet.com/v2/contacts
            Arguments:
            contact_iden -- the iden of the contact to delete
        """
        return self._request("DELETE", HOST + "/contacts/" + contact_iden)

    def getUser(self):
        """ Get this users information
            https://docs.pushbullet.com/v2/users
        """
        return self._request("GET", HOST + "/users/me")

#    def realtime(self, callback):
#        """ Opens a Realtime Event Stream
#            https://docs.pushbullet.com/stream
#            callback will be called with one argument, the JSON response
#            from the server, nop messages are filtered.
#            Arguments:
#            callback -- The function to call on activity
# """#
#
#        url = "wss://stream.pushbullet.com/websocket/" + self.apiKey
#        ws = create_connection(url)
#        while 1:
#            data = ws.recv()
#            data = json.loads(data)
#            if data["type"] != "nop":
#                callback(data)
