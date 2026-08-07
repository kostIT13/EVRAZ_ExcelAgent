import { motion } from 'framer-motion';

export default function TypingIndicator() {
  return (
    <motion.div
      className="typing-indicator"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <motion.span
        className="typing-indicator__dot"
        animate={{ y: [0, -6, 0] }}
        transition={{ repeat: Infinity, duration: 0.8, delay: 0 }}
      />
      <motion.span
        className="typing-indicator__dot"
        animate={{ y: [0, -6, 0] }}
        transition={{ repeat: Infinity, duration: 0.8, delay: 0.15 }}
      />
      <motion.span
        className="typing-indicator__dot"
        animate={{ y: [0, -6, 0] }}
        transition={{ repeat: Infinity, duration: 0.8, delay: 0.3 }}
      />
    </motion.div>
  );
}