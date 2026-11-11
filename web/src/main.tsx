import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { isObsPath, ObsOverlayPage } from "./pages/ObsOverlayPage";
import "./styles.css";

const root = document.getElementById("root")!;
const page = isObsPath() ? <ObsOverlayPage /> : <App />;

createRoot(root).render(<StrictMode>{page}</StrictMode>);
