FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
<<<<<<< HEAD

ARG NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
RUN npm ci --registry="${NPM_CONFIG_REGISTRY}"
=======
RUN npm ci --registry=https://registry.npmmirror.com
>>>>>>> 3238cfc15c7913ff0dd17908b8d7c5ea6b30367d

COPY . .
RUN VITE_API_BASE_URL=/api npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
