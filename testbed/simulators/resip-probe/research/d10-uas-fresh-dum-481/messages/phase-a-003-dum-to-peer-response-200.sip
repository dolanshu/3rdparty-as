SIP/2.0 200 OK
From: <sip:caller@127.0.0.1:47772>;tag=caller-62cd7ef4763c4c14
To: <sip:uas@127.0.0.1:47771>;tag=3487f79b
Call-ID: uas-restart-62cd7ef4763c4c14@127.0.0.1
CSeq: 1 INVITE
Via: SIP/2.0/UDP 127.0.0.1:47772;branch=z9hG4bK-invite-62cd7ef4763c4c14;rport=47772
Record-Route: <sip:127.0.0.1:47771;lr;transport=udp>
Contact: <sip:uas@127.0.0.1:47771>
Allow: INVITE, ACK, CANCEL, OPTIONS, BYE, UPDATE
Content-Type: application/sdp
Content-Length: 159

v=0
o=- 5001 2 IN IP4 127.0.0.1
s=UAS restart negative recovery probe
c=IN IP4 127.0.0.1
t=0 0
m=audio 49172 RTP/AVP 0
a=rtpmap:0 PCMU/8000
a=sendrecv
