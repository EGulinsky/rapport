# syntax=docker/dockerfile:1
FROM node:20-alpine AS builder
ARG BUILD_NUMBER=0
ENV VITE_BUILD_NUMBER=$BUILD_NUMBER
ARG ENV_LABEL=
ENV VITE_ENV_LABEL=$ENV_LABEL
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline
COPY . .
RUN npm run build

FROM nginx:alpine
ARG NGINX_CONF=nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY $NGINX_CONF /etc/nginx/conf.d/default.conf
EXPOSE 80
