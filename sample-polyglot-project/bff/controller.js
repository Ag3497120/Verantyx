exports.getStatus = (req, res) => {
  res.json({ service: 'BFF', status: 'OK' });
};
