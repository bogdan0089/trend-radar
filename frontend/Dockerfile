# Build the SPA, then serve the static files from nginx.
# nginx also proxies /api to the backend, so the browser only ever talks to one
# origin and no CORS negotiation is involved.

FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
