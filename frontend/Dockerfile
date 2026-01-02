# Usamos uma imagem de Node simples
FROM node:22-alpine

WORKDIR /app

# Copiamos apenas os ficheiros de dependências primeiro (Cache eficiente)
COPY package*.json ./

# Instalamos as dependências
RUN npm install

# Copiamos o resto do código
COPY . .

# Expomos a porta do Vite
EXPOSE 5173

# Comando por defeito (Modo Desenvolvimento)
CMD ["npm", "run", "dev"]