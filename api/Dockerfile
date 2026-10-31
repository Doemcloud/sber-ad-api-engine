FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY . .
RUN CGO_ENABLED=0 go build -o /out/api ./cmd/server

FROM alpine:3.20
WORKDIR /app
COPY --from=build /out/api /app/api
ENV PORT=8080 MOCK_DIR=/data/mock STATE_FILE=/state/state.json
EXPOSE 8080
CMD ["/app/api"]
