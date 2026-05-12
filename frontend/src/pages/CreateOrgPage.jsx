import { CreateOrganization } from "@clerk/react";

export default function CreateOrgPage() {
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: "10vh" }}>
      <CreateOrganization
        routing="path"
        path="/create-org"
        afterCreateOrganizationUrl="/onboarding"
        skipInvitationScreen={true}
      />
    </div>
  );
}
