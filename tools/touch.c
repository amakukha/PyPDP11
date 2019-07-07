/* backport of `touch` command from Unix V7 to Unix V6 */
/* written in pre-K&R C */

main(argc,argv)
int argc;
char *argv[];
{
	int i;
	static int force;
	force = 1;
	
	for(i=1; i<argc; ++i)
		if(argv[i][0]=='-' && argv[i][1]=='c' && !argv[i][2])
			force = 0;
		else
			touch(force, argv[i]);
}

touch(force, name)
int force;
char *name;
{
	char stbuff[50];
	char junk[1];
	int fd;
	
	if(stat(name, stbuff) < 0)
		if(force)
			goto create;
		else {
			diag(name);
			diag(": file does not exist\n");
			return;
		}
	
	if(stbuff[9]==0 && stbuff[10]==0 && stbuff[11]==0)	/* st_size == 0 */
		goto create;
	
	if( (fd = open(name, 2)) < 0)
		goto bad;
	
	if( read(fd, junk, 1) < 1) {
		close(fd);
		goto bad;
	}
	seek(fd, 0, 0);
	if( write(fd, junk, 1) < 1 ) {
		close(fd);
		goto bad;
	}
	close(fd);
	return;
	
bad:
	diag(name);
	diag(": cannot touch\n");
	return;

create:
	if( (fd = creat(name, 0666)) < 0)
		goto bad;
	close(fd);
}

diag(s)
char *s;
{
	while(*s)
		write(2,s++,1);
}
