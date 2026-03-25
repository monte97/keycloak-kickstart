FROM quay.io/keycloak/keycloak:26.1 as builder

WORKDIR /opt/keycloak

COPY ./provider/keycloak-webhook-provider-*.jar /opt/keycloak/providers/

RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.1

COPY --from=builder /opt/keycloak/ /opt/keycloak/

EXPOSE 8080

ENTRYPOINT ["/opt/keycloak/bin/kc.sh", "start"]
