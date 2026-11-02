# Production frontend: compiled React assets, no Node/Vite dev server at runtime.
FROM node:24-alpine AS build
WORKDIR /build
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
# Private LAN deployment uses the existing FastAPI endpoints via nginx proxy.
RUN VITE_DATA_MODE=api npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist/ /usr/share/nginx/html/
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 --start-period=5s \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
