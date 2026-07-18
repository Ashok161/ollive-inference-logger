FROM node:20-alpine AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache gettext
COPY apps/web/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY apps/web/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
COPY --from=build /app/dist /usr/share/nginx/html
ENV PORT=80
ENV API_UPSTREAM=http://api:8000
EXPOSE 80
CMD ["/docker-entrypoint.sh"]
