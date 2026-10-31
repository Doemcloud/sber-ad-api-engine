FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_AGENT_URL=http://localhost:8000
ARG VITE_API_URL=http://localhost:8080
ENV VITE_AGENT_URL=$VITE_AGENT_URL VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# адреса API и агента для Content-Security-Policy (connect-src)
ENV API_ORIGIN=http://localhost:8080 AGENT_ORIGIN=http://localhost:8000 NGINX_ENVSUBST_FILTER=_ORIGIN$
EXPOSE 80
