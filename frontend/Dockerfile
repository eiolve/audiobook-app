FROM nginx:1.27.3-alpine

COPY frontend/ /usr/share/nginx/html/
COPY frontend/scripts/entrypoint.sh /docker-entrypoint.d/40-configure-api-url.sh
RUN chmod +x /docker-entrypoint.d/40-configure-api-url.sh

EXPOSE 80
