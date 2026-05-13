import { SignUp } from "@clerk/react";

export default function SignUpPage() {
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: "10vh" }}>
      <SignUp
        routing="path"
        path="/register"
        signInUrl="/login"
        afterSignUpUrl="/create-org"
      />
    </div>
  );
}
