import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import DeadlinePage from "./pages/DeadlinePage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import ProposalPage from "./pages/ProposalPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* Pages that need a logged-in user go inside Layout. */}
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/proposal" element={<ProposalPage />} />
        <Route path="/deadlines" element={<DeadlinePage />} />
      </Route>
    </Routes>
  );
}
