import { motion } from 'framer-motion';

export default function Background() {
  return (
    <div className="bg-particles">
      {[0, 1, 2, 3].map((i) => (
        <motion.div
          key={i}
          className="bg-particles__orb"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.12 }}
          transition={{ duration: 2, delay: i * 0.3 }}
        />
      ))}
    </div>
  );
}