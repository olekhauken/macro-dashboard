# Dockerfile
# ==========
# Brukes av Render.com for å låse Python-versjonen til 3.11.9.
# Render velger automatisk Docker-bygging når denne filen finnes.
#
# python:3.11.9-slim er et offisielt, minimalt image – liten størrelse,
# rask build, og identisk miljø uavhengig av hva Render har som standard.

FROM python:3.11.9-slim

# Sett arbeidsmappe inne i containeren
WORKDIR /app

# Kopier avhengighetslisten først (cacher pip-steget hvis requirements.txt
# ikke har endret seg – raskere re-deploy ved kun kodeendringer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopier resten av koden
COPY . .

# Lag data-mappen slik at scheduler kan skrive market.json
# (containere starter med tomt filsystem – mkdir trengs her)
RUN mkdir -p data/store

# Render setter $PORT dynamisk; gunicorn binder til den
# --workers 1  : én worker passer gratis-tier (begrenset RAM ~512 MB)
# --timeout 120: gir tid til oppstart-fetch av markedsdata
CMD gunicorn app:server --bind 0.0.0.0:$PORT --workers 1 --timeout 120
