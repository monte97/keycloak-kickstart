# Use the official Keycloak image as the base image
FROM quay.io/keycloak/keycloak:26.0 as builder

# Set the working directory inside the container
WORKDIR /opt/keycloak

# Copy the custom provider (JAR file) from the host machine to the Keycloak provider directory
COPY ./provider/keycloak-events-26.0.jar /opt/keycloak/providers/

# Copy the custom theme folder into the Keycloak themes directory
ARG KC_THEME=default
COPY ./themes/${KC_THEME}/ /opt/keycloak/themes/custom-theme/

# Build the Keycloak distribution to include the provider
RUN /opt/keycloak/bin/kc.sh build

# Use the official Keycloak image again for the final image
FROM quay.io/keycloak/keycloak:26.0

# Copy the Keycloak build (which includes the custom provider) from the builder stage
COPY --from=builder /opt/keycloak/ /opt/keycloak/

# Expose Keycloak's port
EXPOSE 8080

# Set the entrypoint to start Keycloak
ENTRYPOINT ["/opt/keycloak/bin/kc.sh", "start"]
