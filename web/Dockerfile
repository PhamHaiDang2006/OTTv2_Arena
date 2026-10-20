FROM node:22-alpine AS build
WORKDIR /app
COPY contracts/ contracts/
COPY engine/fixtures/ engine/fixtures/
COPY web/package.json web/package-lock.json web/
COPY web/replay-viewer/package.json web/replay-viewer/package.json
WORKDIR /app/web
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine AS p1
COPY web/nginx-p1.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist/p1 /usr/share/nginx/html
EXPOSE 8080

FROM nginxinc/nginx-unprivileged:1.28-alpine AS p2
COPY web/nginx-p2.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist/p2 /usr/share/nginx/html/admin
EXPOSE 8080
