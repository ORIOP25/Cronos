# Estágio 1: Build (Construir o site)
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Estágio 2: Production (Servir com Nginx)
FROM nginx:alpine
# Copiar o site construído para a pasta do Nginx
COPY --from=build /app/dist /usr/share/nginx/html
# Copiar a nossa configuração personalizada
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]