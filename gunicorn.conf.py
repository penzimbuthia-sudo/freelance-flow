import os

bind = f"0.0.0.0:{int(os.environ.get('PORT', '10000'))}"
workers = 1
worker_class = "gthread"
threads = 4
timeout = 90
graceful_timeout = 90
# Avoid idle upstream sockets delaying graceful restart on this small service.
keepalive = 0
max_requests = 1000
max_requests_jitter = 100
# Never log bearer token payment URLs, cookies, credentials, or request bodies.
accesslog = None
errorlog = "-"
# Security uses the configured HTTPS origin, not untrusted forwarded headers.
forwarded_allow_ips = ""
