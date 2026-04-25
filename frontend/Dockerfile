# Stage 1: Build the React application
FROM node:20-alpine as build

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm ci

# Copy the rest of the application
COPY . .

# Build the application
# We use the argument passed from docker-compose if needed
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN npm run build

# Stage 2: Serve the build using Nginx
FROM nginx:alpine

# Copy the build output to nginx's serve directory
COPY --from=build /app/build /usr/share/nginx/html

# Expose port 80 (standard for HTTP)
EXPOSE 80

# Default command for nginx
CMD ["nginx", "-g", "daemon off;"]
