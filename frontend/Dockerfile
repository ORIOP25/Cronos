# Shared base for build and dev stages: installs dependencies once. Docker
# builds this stage a single time and both the build and dev stages reuse
# its layers, instead of running `npm ci` twice.
FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# Development dependencies are installed in the build stage only.
FROM deps AS build
COPY . .
ARG VITE_CLERK_PUBLISHABLE_KEY
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_TURNSTILE_SITE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
RUN npm run build

# Vite remains available through docker-compose.dev.yml.
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# nginxinc's unprivileged image listens as nginx on port 8080.
FROM nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6 AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080

# CI uses Clerk's reserved test instance, whose accounts.dev origins must not
# be present in the production image's browser policy.
FROM runtime AS ci
COPY nginx.ci.conf /etc/nginx/conf.d/default.conf

# Local development uses Clerk's accounts.dev instance from .env.local. Keep
# those origins out of the production runtime policy.
FROM runtime AS local
COPY nginx.local.conf /etc/nginx/conf.d/default.conf

# The unqualified image is always the production policy. CI and local builds
# opt into their explicit targets above.
FROM runtime AS production
