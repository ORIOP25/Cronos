import { SignIn } from "@clerk/react";

export default function SignInPage() {
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: "10vh" }}>
      <SignIn
        routing="path"
        path="/login"
        signUpUrl="/register"
      />
    </div>
  );
}
