FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000
# Dev server keeps hackathon iteration fast; switch to build+start for a hardened demo.
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3000"]
