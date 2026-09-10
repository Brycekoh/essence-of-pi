# The frontend as a production build, for docker compose.
#
# NEXT_PUBLIC_API_URL is inlined into the JavaScript bundle at *build* time, so
# it is a build argument rather than a runtime variable. The browser -- not
# this container -- calls the API, which is why the default is localhost and
# not the compose service name.

FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
